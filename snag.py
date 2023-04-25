import argparse
import datetime
import time
from dataclasses import dataclass
import json
from enum import Enum
import urllib.error
from urllib import request
import subprocess
import shlex
import os
import configparser
from pathlib import Path
import math
from typing import Tuple, List, Dict
import sys


class ForecastSource(Enum):
    NATIONAL = 0
    REGIONAL = 1
    POSTCODE = 2


@dataclass
class SnagTask:
    """
    Groups all the properties needed for snag to schedule, run, and report
    """
    cmd: str
    due_by: str
    outward_code: str = '0'
    co2_actual: int = 0
    co2_worst: int = 0
    duration_scheduled: int = 10
    duration_actual: float = 0
    has_run: bool = False
    base_host: str = "https://api.carbonintensity.org.uk"
    tolerance: int = 5
    time_offset: int = 0
    shell: bool = False
    echo_out: bool = False

    def __post_init__(self):
        # Scale the due by time factoring duration and time offset
        due_by_dt: datetime.datetime = datetime.datetime.fromisoformat(self.due_by)
        due_by_dt = due_by_dt - datetime.timedelta(minutes=(self.time_offset + self.duration_scheduled))
        self.due_by = due_by_dt.strftime("%Y-%m-%dT%H:%M")


def query_api(url: str, verbose: bool = False) -> Dict:
    """
    Send a query to National Grid API and return the JSON representation
    :param url: full string to fetch from
    :return: JSON return
    """
    RETRIES = 3
    success: bool = False
    attempts: int = 0
    delay: int = 1

    while not success and attempts < RETRIES:
        if verbose:
            print(f"    Fetching: {url} ... ", end="")

        attempts += 1
        try:
            page = request.urlopen(url)
            if verbose:
                print("Done!")
            success = True
        except urllib.error.HTTPError:
            if verbose:
                print(f"Failed. Sleeping {delay} s")
            time.sleep(delay)
            delay *= 2
            continue

    if not success:
        print("Fetch from National Grid failed. Exiting.")
        exit(1)

    try:
        data = page.read()
        encoding = page.info().get_content_charset("utf-8")
        return_json: Dict = json.loads(data.decode(encoding))
    except Exception as e:
        print(f"Unhandled error parsing JSON: {e}")
        exit(1)

    return return_json


def decompose_fw48(data: Dict,
                   forecast_type: ForecastSource) -> List[Tuple[str, int]]:
    """
    Decompose a 48 hour forecast into a list of (ISO8601, intensity) pairs.
    Datastructure dependent on source (National, (Regional | Postcode))
    :param data: JSON from NG API
    :param forecast_type: location information type
    :param verbose: verbose output
    :return: (ISO8601, int) time and intensity pairs
    """
    ret_list: List[Tuple[str, int]] = []

    if forecast_type != ForecastSource.NATIONAL:
        extract = data["data"]["data"]
    else:
        extract = data["data"]

    # The NG API may return the previous 30 minute interval as the first
    # entry. If this is the case, then remove this entry.
    time_first: datetime.datetime = datetime.datetime.fromisoformat(extract[0]["from"].rstrip('Z'))
    time_now: datetime.datetime = half_hour_floor(datetime.datetime.now())
    if time_first < time_now:
        extract = extract[1:]

    for timepoint in extract:
        dt: str = timepoint["from"].rstrip('Z')
        intensity: int = int(timepoint["intensity"]["forecast"])
        ret_list.append((dt, intensity))

    return ret_list


def half_hour_floor(dt: datetime.datetime) -> datetime.datetime:
    """
    Round a datetime object down to nearest 30 minute
    :param dt: datetime object to round
    :return: datetime rounded down to nearest 30 min
    """
    minute_mod30: int = dt.minute % 30
    if minute_mod30 or dt.second or dt.microsecond:
        dt = (dt - datetime.timedelta(minutes=minute_mod30,
                                      seconds=dt.second,
                                      microseconds=dt.microsecond))
    return dt


def half_hour_ceil(dt: datetime.datetime) -> datetime.datetime:
    """
    Round a datetime object up to nearest 30 minute
    :param dt: datetime object to round
    :return: datetime rounded up to nearest 30 min
    """
    dt_floor: datetime.datetime = half_hour_floor(dt)
    return dt_floor + datetime.timedelta(minutes=30)


def run_task(task: SnagTask, verbose: bool = False) -> None:
    """
    Run the task that we've scheduled
    :param task: SnagTask object with the required data
    :param verbose: verbose output
    """
    if task.shell:
        print(f"    Running task in shell: {task.cmd}")
        cmd: str = task.cmd
    else:
        print(f"    Running task: {task.cmd}")
        cmd: List[str] = shlex.split(task.cmd)

    start: float = time.time()
    p = subprocess.run(cmd, shell=task.shell,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    task.duration_actual = time.time() - start
    task.has_run = True

    if task.echo_out:
        print(p.stdout)


def weight_timepoints(task: SnagTask, timepoints: List[Tuple[str, int]]) -> None:
    """
    Weight the timepoints for intensity for a given task duration and offset
    :param task: the SnagTask object, this contains the needed task data
    :param timepoints: the raw NG API data
    :return: None, the timepoints list is modified in place
    """
    window: List[int] = []
    leading: int = 0
    mid: int = 0
    residual: int = task.duration_scheduled

    # Determine how the task will be split up. If there is an offset, then the
    # first segment will be (30 mins - offset), the middle segments will be
    # 30 mins each, then mop up any remaining minutes.
    if task.time_offset:
        leading = 30 - task.time_offset
        window.append(leading)
        residual -= leading

    mid = int(residual / 30)
    window += mid * [30]
    residual -= mid * 30
    window.append(residual)

    # Use this window to  scale the raw time point information. This will
    # implicitly shrink the timepoints list (overflow at the end), but values
    # here will not be used anyway as the task must have started before that
    for idx in range(len(timepoints) - len(window)):
        weighted_avg: int = sum([a * b[1] for a, b in zip(window, timepoints[idx:(idx + len(window))])])
        weighted_avg = int(weighted_avg / sum(window))
        timepoints[idx] = (timepoints[idx][0], weighted_avg)


def schedule_task(task: SnagTask, verbose: bool = False) -> None:
    """
    Fetch the forecast (national, regional, or by outward code) and schedule
    for time when CO2 intensity is lowest. Capture worst case intensity for
    reporting as well.
    :param task: SnagTask dataclass with all information required
    :param verbose: verbosity flag to stdout
    :return: None
    """

    # Switch fetch source dependent on information provided. 0 -> national,
    # 1-17: regional, other: outward code
    time_now: datetime.datetime = datetime.datetime.now()
    time_now_floor: str = half_hour_floor(time_now).isoformat()
    get_dest: str = ""
    forecast_type: ForecastSource = ForecastSource.NATIONAL

    if verbose:
        print(f"Scheduling [{task.cmd}]")
        print(f"    Time now       : {time_now.strftime('%Y-%m-%d %H:%M')}")
        print(f"    Due by         : {' '.join(task.due_by.split('T'))}")

    try:
        numeric: int = int(task.outward_code)
        if numeric == 0:
            get_dest = f"{task.base_host}/intensity/{time_now_floor}Z/fw48h"
            pass  # This is the default national ID
        elif 0 < numeric < 18:
            get_dest = f"{task.base_host}/regional/intensity/{time_now_floor}Z/fw48h/regionid/{numeric}"
            forecast_type = ForecastSource.REGIONAL
        else:
            print("Region code must be between 1 and 17")
            exit(1)
    except ValueError:  # Postcode
        get_dest = f"{task.base_host}/regional/intensity/{time_now_floor}Z/fw48h/postcode/{task.outward_code}"
        forecast_type = ForecastSource.POSTCODE

    # Fetch from the NG API, decompose into list of (time, intensity) points
    ng_data: Dict = query_api(get_dest, verbose)
    timepoints: List[Tuple[str, int]] = decompose_fw48(ng_data, forecast_type)

    # If the task will cross a 30 minute boundary, then calculate the weighted
    # mean intensity over that time period.
    crosses_boundary: bool = (task.duration_scheduled + task.time_offset > 30) or (task.duration_scheduled > 30)
    if crosses_boundary:
        weight_timepoints(task, timepoints)

    # Go through forecast up until the "due_by" time, and schedule for lowest
    # CO2 intensity, accounting for intensity tolerance. Capture highest
    # intensity in forecast for reporting.
    tp_now: str = timepoints[0][0]
    tp_lowest: Tuple[str, int] = timepoints[0]
    intensity_highest: int = task.co2_worst
    due_by_dt: datetime.datetime = datetime.datetime.fromisoformat(task.due_by)
    for tm_str, intensity in timepoints:
        tm_dt: datetime.datetime = datetime.datetime.fromisoformat(tm_str)
        if tm_dt > due_by_dt:
            break

        lowest_scaled: int = int(tp_lowest[1] * (1 - task.tolerance / 100))
        if intensity < lowest_scaled:
            tp_lowest = (tm_str, intensity)

        if intensity > intensity_highest:
            intensity_highest = intensity

    task.co2_worst = intensity_highest
    time_scheduled: str = tp_lowest[0]

    if verbose:
        print(f"    Scheduled for  : {time_scheduled} @ {tp_lowest[1]} gCO2/kWh")

    # REVISIT For long tasks, the predicted intensity will drift from the
    # actual value. Could thread here to get the real intensity over time.
    if time_scheduled == tp_now:
        task.time_ran = time_scheduled
        task.co2_actual = tp_lowest[1]
        run_task(task, verbose)


def sleep_until_next(offset: int = 0, verbose: bool = False) -> None:
    """
    Sleep until the next 30 minute interval
    """
    next_wake: datetime.datetime = half_hour_ceil(datetime.datetime.now())
    next_wake = next_wake + datetime.timedelta(minutes=offset)
    sleep_time: datetime.timedelta = next_wake - datetime.datetime.now()
    if verbose:
        wake_time: str = next_wake.strftime("%Y-%m-%d %H:%M")
        print(f"    Sleeping until : {wake_time} ({int(sleep_time.seconds / 60)}m{sleep_time.seconds % 60}s)")
    time.sleep(sleep_time.seconds)


def main():
    if sys.version_info < (3, 7):
        print(f"snag requires Python >3.6. Found {sys.version_info[0]}.{sys.version_info[1]}. Exiting.")
        exit(1)

    try:
        home_dir = os.environ["HOME"]
    except KeyError:
        home_dir = ""

    parser = argparse.ArgumentParser(
        prog="snag",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Scheduling your task to minimise its carbon impact.")

    # Optionals - the defaults are loaded from the configuration file, anything
    # specified here will override the configuration file values.
    parser.add_argument("-a", "--base_host",
                        help="National Grid API base host path.")
    parser.add_argument("-c", "--cfg",
                        default=f'{home_dir}/.config/snag/snag.ini',
                        help="Path to configuration file. Any supplied arguments will override values here.")
    parser.add_argument("-d", "--delay",
                        help="Offset start time from 30 min interval, in minutes.")
    parser.add_argument("-e", "--echo_out", action="store_true",
                        help="Print the task's stdout/stderr to stdout when complete.")
    parser.add_argument("-l", "--duration", default=10, type=float,
                        help="Task's duration in minutes.")
    parser.add_argument("-oc", "--outward_code",
                        help="Outward (first) part of UK postcode, e.g. NW1, or region code defined in National Grid API.")
    parser.add_argument("-sh", "--shell", action="store_true",
                        help="Run task in shell. Reported duration may not be accurate.")
    parser.add_argument("-t", "--tolerance",
                        help="Minimum gCO2/kWh saving to reschedule (%%).")
    parser.add_argument("-v", "--verbose", action="store_const", const="yes",
                        help="Verbose output.")
    parser.add_argument("--version", action="version",
                        version="%(prog)s 0.1.0\n\
                                 Copyright © 2023 Angus Logan\n\
                                 License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.\n\
                                 This is free software: you are free to change and redistribute it.\n\
                                 There is NO WARRANTY, to the extent permitted by law.\n\n\
                                 Written by Angus Logan, for Bear and Moose.")

    # Required arguments
    parser.add_argument("due_by",
                        help="Time the task is due by. This can be in ISO8601 format (YYYY-MM-DDTHH:MMZ), or the number of hours ahead of the current time.")
    parser.add_argument("cmd", nargs='+',
                        help="The command to be run.")

    args = parser.parse_args()

    # Load configuration from file, and then override with arguments. If the
    # config file does not exist, then create with default values
    config: configparser.ConfigParser = configparser.ConfigParser()
    if os.path.isfile(args.cfg):
        try:
            config.read(args.cfg)
        except OSError as e:
            print(f"Failed to read configuration file {args.cfg}: {e}")
            exit(1)
    else:
        config["SNAG"] = {"delay": "0",
                          "base_host": "https://api.carbonintensity.org.uk",
                          "tolerance": "5",
                          "outward_code": "0",
                          "verbose": "no",
                          "echo_out": "no"}
        try:
            cfg_dir = Path(args.cfg).parents[0]
            p = Path(cfg_dir)
            p.mkdir(parents=True)
            with open(args.cfg, 'w') as f:
                config.write(f)
            if args.verbose:
                print(f"Created configuration file: {args.cfg}")
        except OSError as e:
            print(f"Failed to create configuration file {args.cfg}: {e}")
            exit(1)

    if args.delay:
        config["SNAG"]["delay"] = args.delay
    if args.verbose:
        config["SNAG"]["verbose"] = args.verbose
    if args.outward_code:
        config["SNAG"]["outward_code"] = args.outward_code
    if args.tolerance:
        config["SNAG"]["tolerance"] = args.tolerance
    if args.base_host:
        config["SNAG"]["base_host"] = args.base_host
    if args.echo_out:
        config["SNAG"]["echo_out"] = args.echo_out

    verbose: bool = config["SNAG"]["verbose"] == "yes"
    echo_out: bool = config["SNAG"]["echo_out"] == "yes"

    # If the due_by argument has been given as a numeric value, then convert
    # to an ISO8601 format time ahead of now. Otherwise, strip trailing Z if
    # present as datetime.datetime.isoformat does not handle it correctly.
    due_by: str = args.due_by
    try:
        time_ahead: float = float(args.due_by)
        time_now: datetime.datetime = datetime.datetime.now()
        due_by = (datetime.datetime.now() + datetime.timedelta(hours=time_ahead)).isoformat()
    except ValueError:
        due_by = due_by.rstrip('Z')

    # Construct the task object, and start scheduling
    cmd = ''.join(args.cmd)
    task = SnagTask(cmd=cmd, due_by=due_by,
                    duration_scheduled=math.ceil(args.duration),
                    base_host=config["SNAG"]["base_host"],
                    outward_code=config["SNAG"]["outward_code"],
                    time_offset=int(config["SNAG"]["delay"]),
                    tolerance=int(config["SNAG"]["tolerance"]),
                    shell=args.shell,
                    echo_out=echo_out)
    schedule_task(task, verbose)

    while not task.has_run:
        sleep_until_next(int(config["SNAG"]["delay"]), verbose)
        schedule_task(task, verbose)

    time_now: str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    potential_saving: int = abs(int(((task.co2_actual / task.co2_worst) - 1) * 100))
    print(f"snag @ {time_now}")
    print(f"    Task:       {task.cmd}")
    print(f"    Duration:   {task.duration_actual:.2f} s @ {task.co2_actual} gCO2/kWh")
    print(f"    CO2 saving: {potential_saving}%")


if __name__ == "__main__":
    main()
