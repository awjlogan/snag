<h1 style="text-align: center;"> 🌭 snag</h1>
<h4 style="text-align: center;">Not a sausage of CO<sub>2</sub></h4>

`snag` schedules your non-interactive tasks to be run when the *carbon intensity* (the amount of carbon produced per unit of energy) is lowest. You tell it:

  - When you want your task done by
  - How long your task takes

and it will work out the best time to do it! When your task finishes, it will report the carbon saving for your task.

`snag` uses [National Grid's Carbon Intensity API](https://www.carbonintensity.org.uk) to get a 48 hour ahead forecast.

## Usage

### Basic usage

It is a Python standard library only implementation with no external dependencies - clone the repository, and you are good to go! The minimum requirement to run `snag` is:

``` > python snag.py <DUE TIME> <COMMAND TO RUN> ```

*Due time* can be specified as an absolute value in ISO8601 (YYYY-MM-DDTHH:MM) format, or as a number of hours ahead from the current time.

### 🥩 `sizzler` - a simple API mirror

If you are running lots of instances of `snag` consider mirroring the National Grid API to a local server as each request from `snag` is the same. `sizzler` is a simple HTTP mirror - it will cache the last response for each requested region. It can be invoked by:

```python sizzler.py <port>```

where `port` is the server's port. If `port` is not specified, the default is `8080`.

**CAUTION**: this is a very basic server, and does not have any security provision beyond Python's [http.server](https://docs.python.org/3/library/http.server.html) intrinsic model. It should only be used in a trusted environment.

### More advanced options

`snag` provides two configuration methods:

  1. A simple command line interface
  2. A "global" configuration file for common options. These can be overridden if desired.

#### Command line options

The following switches are available on `snag`'s command line. They can also be accessed by running `snag.py --help`.

| Switch              | Arguments                  | Default                            | Description                  |
| ------------------- | :------------------------- | :--------------------------------- |:--------------------------- |
| -a, --base_host     | API host address           | https://api.carbonintensity.org.uk | Address of National Grid API |
| -c, --cfg           | Path to configuration file | $HOME/.config/snag/snag.ini        | Path of the global configuration file |
| -d, --delay         | 0 \< delay \< 30           | 0                                  | Offset in minutes from 30 minute interval |
| -e, --echo_out      | *None*                     | *False*                            | If set, the task's `stdout`/`stderr` will be echoed to `snag`'s `stdout` when complete |
| -oc, --outward_code | Outward, or regional code  | *None*                             | The outward (first) part of postcode, or API defined regional code. If not specified, the national forecast will be used |
| -sh, --shell        | *None*                     | *False*                            | Run the task in shell. Reported duration may be incorrect |
| -t, --tolerance     | 0 \< tolerance \< 100      | 5                                  | Minimum carbon saving to reschedule to later time |
| -v, --verbose       | *None*                     | *False*                            | Verbose output from `snag` |

#### Configuration File

This is a simple "ini" style (KEY: VALUE) file using Python's [ConfigParser](https://docs.python.org/3/library/configparser.html), with all options contained in a single section: `SNAG`. If the configuration file does not exist, `snag` will create a file with a default configuration. The default location for the configuration file is `$HOME/.config/snag/snag.ini` The options available here are:

  - `base_host`
  - `delay`
  - `echo_out`
  - `outward_code`
  - `tolerance`
  - `verbose`
