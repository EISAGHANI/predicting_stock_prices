"""The eleven day-trader skills, described for the web UI.

Every skill is a script in vendor/day_trader_skill. Each Action below is one way
to call it: the fixed arguments, the form fields that become flags, the extra
arguments demo mode adds (recorded data and a pinned clock), and plain-English
text that tells a beginner what happens behind the scenes.

Paths in `demo` arguments use {fix} for the vendored test fixtures.
"""
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

DEMO_DAY = "2026-10-19"
DEMO_DAY_LABEL = "Oct 19 2026"
FIX = "{fix}"
DAILY_DEMO_SYMBOLS = "BLK, CI, XOM, HD, KO, CCL, RCL, F, JPM, GE, BAC, PLUG, MS, RIVN, PNC, TSLA, NVDA, MSFT, AMZN"


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"            # ticker | tickers | number | int | select | bool | time | text
    flag: Optional[str] = None    # None: a positional argument
    default: object = None
    demo_default: object = None   # overrides `default` in demo mode
    choices: tuple = ()           # (value, label) pairs for kind="select"
    help: str = ""
    placeholder: str = ""
    required: bool = False
    join: Optional[str] = None    # tickers: one comma-joined argument instead of one per ticker
    when_false: bool = False      # bool: pass the flag when unticked (e.g. --no-write)
    fmt: str = "{}"               # how the value is written into the argument
    modes: tuple = ("demo", "live")
    advanced: bool = False
    arg: bool = True              # False: only read by the action's `extra` builder
    min: Optional[float] = None
    max: Optional[float] = None


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    summary: str
    steps: tuple                  # what happens behind the scenes, in order
    args: tuple = ()              # fixed leading arguments (the subcommand)
    fields: tuple = ()
    demo: tuple = ()              # extra arguments in demo mode (recorded data, pinned clock)
    modes: tuple = ("demo", "live")
    demo_note: str = ""
    sources: tuple = ()           # where live data comes from
    reads: tuple = ()             # files in trader/ it reads
    writes: tuple = ()            # files in trader/ it may write
    exit_codes: dict = field(default_factory=dict)
    slow: str = ""                # a warning when it can take minutes
    needs_sec: bool = False
    extra: Optional[Callable] = None   # values -> extra arguments, for flags built from several fields


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    script: str
    tagline: str
    plain: str                    # the whole skill in a few plain sentences
    actions: tuple
    step: Optional[int] = None    # position in the trade journey; None for the research tools
    output: str = ""              # the file that shows this step is done
    next: Optional[str] = None


# Reused field definitions ---------------------------------------------------------

def _save(path, default=True):
    return Field("write", "Save the result for the next skill", "bool", "--write", default,
                 help=f"Writes {path} so the next skill in the chain can read it.")


def _demo_clock(times, default, help_text="Demo mode replays a real day. Pick the moment to look at it."):
    return Field("demo_now", "Pretend the clock is (New York time)", "select", "--now", default,
                 choices=tuple(times), help=help_text, fmt=DEMO_DAY + " {}", modes=("demo",))


YAHOO = "Yahoo Finance price charts (free, unofficial, can lag a little)"
NOW_1016 = ("--now", f"{DEMO_DAY} 10:16")


def _stop_and_target(v):
    extra = []
    if v.get("stop_price") is not None:
        extra += ["--stop", f"price:{v['stop_price']}"]
    if v.get("target_price") is not None:
        extra += ["--target", f"price:{v['target_price']}"]
    return extra


def _price_alert(v):
    return [f"--{v['direction']}", str(v["price"])]


# The skills -------------------------------------------------------------------

SKILLS = (
    Skill(
        id="scanner", step=1, name="Chart Scanner", script="trader-scanner/scan.py",
        tagline="Finds charts that match a trading pattern.",
        plain=("Looking through 5,000 charts by hand takes all day. The scanner downloads them and keeps only "
               "the ones that match a simple rule, like \"the price just climbed above its range from the "
               "first 15 minutes of the day\". A match is not a tip to buy: it is a short list to look at."),
        output="watchlist.json", next="news",
        actions=(
            Action(
                id="orb", label="Opening-range breakouts", args=("orb",),
                summary="Lists stocks whose price closed above the high of their first 15 minutes of trading today.",
                steps=(
                    "Work out the opening range: the highest and lowest price in the first 15 minutes after the 9:30 AM open.",
                    "Quick pass: download today's 5-minute closing prices, 20 stocks per request, and keep any stock that closed above that range.",
                    "Careful pass: for each of those, download the full chart (highs and lows) to confirm a 5-minute candle really closed above the range high.",
                    "List the matches with the time of the breakout and how far above the range they are.",
                    "Save them to trader/watchlist.json for the News Monitor and the Entry Timer.",
                ),
                fields=(
                    Field("symbols", "Only these stocks (optional)", "tickers", "--symbols", join=",",
                          placeholder="e.g. TSLA, NVDA, AMD",
                          help="Leave empty to scan the whole stock list (build it first with \"All US stocks\"). "
                               "A short list is much faster."),
                    _demo_clock((("09:55", "9:55 AM"), ("10:05", "10:05 AM"), ("10:15", "10:15 AM (the reel)")), "10:15"),
                    Field("min_price", "Ignore stocks cheaper than ($)", "number", "--min-price", 5, min=0,
                          help="Very cheap stocks jump around a lot. $5 is the usual floor."),
                    Field("show", "How many matches to print", "int", "--show", 25, min=1, max=500, advanced=True),
                ),
                demo=("--offline", f"{FIX}/trader-scanner/wall5m-2026-10-19.json.gz"),
                demo_note="Replays the real 10:15 AM scan of Monday Oct 19 2026 over 234 charts. No internet needed.",
                sources=(YAHOO,), reads=("universe.txt", "config.json"), writes=("watchlist.json",),
                exit_codes={1: "No stock matched, or the scan could not run (the reason is in the log). Before 9:50 AM New York time, at weekends and after the close there is nothing to find."},
                slow="The whole market takes about 4 minutes. A short list takes seconds.",
            ),
            Action(
                id="daily", label="Pre-market setups", args=("daily",),
                summary="Before the market opens, checks each stock's daily closing prices for five classic chart patterns.",
                steps=(
                    "Download the last few months of daily closing prices, 20 stocks per request.",
                    "Drop stocks that are too cheap or trade too little to be easy to buy and sell.",
                    "Test five patterns on the closes: a new 20-day high, a bull flag, back above the 20-day average, oversold (RSI under 30) and an oversold bounce.",
                    "List the matches, the most traded first, and save them to trader/watchlist.json.",
                ),
                fields=(
                    Field("symbols", "Only these stocks (optional)", "tickers", "--symbols", join=",",
                          demo_default=DAILY_DEMO_SYMBOLS, placeholder="e.g. TSLA, NVDA, AMD, AAPL, KO",
                          help="Leave empty to scan the whole stock list (build it first with \"All US stocks\"). "
                               "Demo mode has recorded charts for the 19 stocks filled in."),
                    Field("limit", "Scan only the first N stocks of the list", "int", "--limit", min=1, advanced=True),
                    Field("min_price", "Ignore stocks cheaper than ($)", "number", "--min-price", 5, min=0, advanced=True),
                ),
                demo=("--offline", f"{FIX}/trader-scanner/daily-spark-2026-10-19.json", "--now", f"{DEMO_DAY} 09:00"),
                demo_note="Uses the real daily charts of 19 stocks as they stood before the open on Oct 19 2026.",
                sources=(YAHOO,), reads=("universe.txt",), writes=("watchlist.json",),
                exit_codes={1: "No stock matched a pattern, or the scan could not run (see the log)."},
                slow="The whole market takes 2 to 3 minutes.",
            ),
            Action(
                id="universe", label="All US stocks", args=("universe",),
                summary="Builds the list of every ordinary US-listed stock (about 5,900) that the scans can go through.",
                steps=(
                    "Download Nasdaq Trader's two official lists of every listed security.",
                    "Remove ETFs, test issues, warrants, units, rights, notes and preferred shares.",
                    "Keep common stocks, ordinary shares and ADRs (foreign companies listed in the US).",
                    "Save the list to trader/universe.txt. Running it once a week is plenty.",
                ),
                demo=("--offline", f"{FIX}/trader-scanner/symdir"),
                demo_note="Uses a trimmed copy of the Oct 19 2026 Nasdaq Trader lists.",
                sources=("Nasdaq Trader symbol directory (nasdaqtrader.com)",), writes=("universe.txt",),
            ),
        ),
    ),
    Skill(
        id="news", step=2, name="News Monitor", script="trader-news/news.py",
        tagline="Checks the headlines and filings before you trade.",
        plain=("A chart can look perfect an hour before bad news. This skill reads the latest Yahoo Finance "
               "headlines and the official filings companies send to the SEC (the US market regulator), "
               "labels each one (earnings, deal, lawsuit...) and shows how far each stock has moved today. "
               "It only shows what is new since the last check."),
        output="state/news.json", next="entry",
        actions=(
            Action(
                id="check", label="Check the news",
                summary="Shows the new headlines and SEC filings for your stocks, newest first, in New York time.",
                steps=(
                    "Decide which stocks to check: the ones you type, or else the scanner's watchlist, your plan and your holdings.",
                    "Download each stock's Yahoo Finance headline feed.",
                    "Download each company's recent 8-K filings from SEC EDGAR (the official \"something important happened\" report).",
                    "Get today's price and compare it with yesterday's close. A move of 3% or more is marked MOVING.",
                    "Tag every item (earnings, analyst, deal, legal, halt...), hide anything already shown before, and list the rest newest first.",
                ),
                fields=(
                    Field("tickers", "Stocks to check", "tickers", "--tickers", demo_default="TSLA",
                          placeholder="e.g. TSLA NVDA",
                          help="Leave empty to use the scanner's watchlist, your plan and your holdings. "
                               "Demo mode has recorded news for TSLA, AAPL and KO."),
                    Field("hours", "Only items from the last (hours)", "number", "--hours", 48, demo_default=12, min=1, max=720),
                    Field("sec", "Include SEC filings", "bool", "--no-sec", True, when_false=True,
                          help="Needs your name and email in Settings (the SEC asks every visitor to identify themselves)."),
                    Field("show_all", "Show items I've already seen", "bool", "--all", False),
                ),
                demo=("--offline", f"{FIX}/trader-news", "--now", f"{DEMO_DAY}T10:15:00-04:00",
                      "--user-agent", "Demo demo@example.org"),
                demo_note="Replays the real headlines and filings as they stood at 10:15 AM on Oct 19 2026.",
                sources=("Yahoo Finance headline feeds", "SEC EDGAR filings (sec.gov)", YAHOO),
                reads=("watchlist.json", "plan.json", "portfolio.json", "config.json"), writes=("state/news.json",),
                exit_codes={1: "Nothing new since the last check. Tick \"Show items I've already seen\" to see them again."},
            ),
        ),
    ),
    Skill(
        id="entry", step=3, name="Entry Timer", script="trader-entry/entry.py",
        tagline="Says the exact moment the setup triggers.",
        plain=("A price that pokes above a line for a few seconds does not count. The Entry Timer waits for a "
               "whole 5-minute candle to finish and close above the line, then reports the time and the price. "
               "It never buys anything: it tells you when a trader following this rule would get in."),
        output="entry.json", next="exit",
        actions=(
            Action(
                id="check", label="Check a stock", args=("check",),
                summary="Says whether the setup has triggered yet: waiting (and how far away), triggered, or too late for today.",
                steps=(
                    "Download today's 5-minute (or 1-minute) price candles for the stock.",
                    "Build the opening range: the high and low of the first 15 minutes (the 9:30, 9:35 and 9:40 candles).",
                    "Walk through the finished candles one by one. A candle still forming is ignored.",
                    "The trigger is the first candle that CLOSES above the range high (or above your own price level).",
                    "Report waiting, triggered or expired, and save the result to trader/entry.json for the Exit Planner.",
                ),
                fields=(
                    Field("symbol", "Stock", "ticker", None, "TSLA", required=True,
                          help="Demo mode has the recorded candles of TSLA only."),
                    _demo_clock((("09:44", "9:44 AM: range still forming"), ("10:12", "10:12 AM: waiting"),
                                 ("10:15", "10:15 AM: the breakout"), ("15:40", "3:40 PM: too late")), "10:15"),
                    Field("setup", "Setup", "select", "--setup", "orb",
                          choices=(("orb", "Opening-range breakout"), ("level", "Close above my own price")),
                          help="An opening-range breakout uses the first 15 minutes. \"My own price\" needs the price below."),
                    Field("level", "My own price level ($)", "number", "--level", min=0,
                          help="Only for \"Close above my own price\", e.g. a 20-day high from the scanner."),
                    Field("interval", "Candle size", "select", "--interval", "5m",
                          choices=(("5m", "5 minutes"), ("1m", "1 minute")), advanced=True),
                    Field("min_volume_x", "Also need volume of at least (x the range's average)", "number",
                          "--min-volume-x", min=0, advanced=True,
                          help="e.g. 1.5 means the trigger candle must trade 1.5 times the shares of an average range candle."),
                    _save("trader/entry.json"),
                ),
                demo=("--offline", f"{FIX}/trader-entry/TSLA-2026-10-19-5m.json"),
                demo_note="Replays TSLA's real 5-minute candles of Oct 19 2026.",
                sources=(YAHOO,), reads=("config.json",), writes=("entry.json",),
                exit_codes={1: "Not triggered: still waiting, expired, the market is closed, or there was no data (see the log)."},
            ),
            Action(
                id="watch", label="Watch candle by candle", args=("watch",),
                summary="Keeps watching, prints one line per finished candle, and stops the moment the setup triggers.",
                steps=(
                    "Download the candles, then wait for each new 5-minute candle to finish.",
                    "After every candle, print one line: where the price closed compared with the range high.",
                    "Stop at the first close above the range high and save trader/entry.json, or stop when it is too late in the day.",
                ),
                fields=(
                    Field("symbol", "Stock", "ticker", None, "TSLA", required=True),
                    _demo_clock((("09:50", "9:50 AM"),), "09:50",
                                "In demo mode the day is replayed from 9:50 AM in fast-forward, candle by candle."),
                    Field("until", "Stop watching at (New York time)", "time", "--until", "15:30"),
                ),
                demo=("--offline", f"{FIX}/trader-entry/TSLA-2026-10-19-5m.json"),
                demo_note="Fast-forwards through TSLA's real candles of Oct 19 2026 from 9:50 AM.",
                sources=(YAHOO,), reads=("config.json",), writes=("entry.json",),
                exit_codes={1: "The setup expired or the market is closed: nothing triggered."},
                slow="Live, this waits for real candles to finish and can run for hours. Press Stop to end it.",
            ),
            Action(
                id="watchlist", label="Check the whole watchlist", args=("watchlist",),
                summary="Runs the check on every stock the scanner saved.",
                steps=(
                    "Read the stocks from trader/watchlist.json (written by the Chart Scanner).",
                    "Check each one as above and print its status in one line.",
                ),
                modes=("live",), sources=(YAHOO,), reads=("watchlist.json", "config.json"),
                exit_codes={1: "None of them has triggered."},
            ),
        ),
    ),
    Skill(
        id="exit", step=4, name="Exit Planner", script="trader-exit/exit.py",
        tagline="Sets the stop and the target before you buy.",
        plain=("Deciding when to sell in the middle of a fast move is how people lose money. The Exit Planner "
               "writes down two prices before anything is bought: the stop (\"if it falls here, the idea was "
               "wrong, get out\") and the target (\"if it reaches here, take the profit\"). It also sets a time "
               "to be out by, so nothing is held overnight."),
        output="plan.json", next="timemachine",
        actions=(
            Action(
                id="plan", label="Make the plan", args=("plan",),
                summary="Turns the entry signal into a full plan: entry price, stop, target, risk per share and a time to be out by.",
                steps=(
                    "Read the entry signal from trader/entry.json (the price and time it triggered, and the opening range).",
                    "Place the stop. By default it goes halfway down the opening range, rounded down to the cent.",
                    "Risk per share = entry price minus stop price. This is \"1R\".",
                    "Place the target a multiple of that risk above the entry (2R by default).",
                    "Refuse plans that make no sense: a stop above the entry, or a stop so tight that normal wiggles would hit it.",
                    "Save the plan to trader/plan.json for the Time Machine, the Budget Manager and Price Alerts.",
                ),
                fields=(
                    Field("stop", "Where the stop goes", "select", "--stop", "or-mid",
                          choices=(("or-mid", "Middle of the opening range"), ("or-low", "Bottom of the opening range (wider)"),
                                   ("pct:0.5", "0.5% under the entry"), ("pct:1", "1% under the entry"),
                                   ("pct:2", "2% under the entry"), ("atr:1", "1x ATR under the entry"),
                                   ("atr:1.5", "1.5x ATR under the entry"), ("atr:2", "2x ATR under the entry")),
                          help="ATR (average true range) is how much the price typically moves in one candle."),
                    Field("target", "Where the target goes", "select", "--target", "2R", demo_default="1R",
                          choices=(("1R", "1R: as far up as the stop is down"), ("1.5R", "1.5R"),
                                   ("2R", "2R: twice as far up as the stop is down"), ("3R", "3R")),
                          help="R is the risk per share. A 2R target aims to make twice what the stop would lose."),
                    Field("stop_price", "Or: my own stop price ($)", "number", arg=False, min=0, advanced=True,
                          help="Overrides the choice above."),
                    Field("target_price", "Or: my own target price ($)", "number", arg=False, min=0, advanced=True,
                          help="Overrides the choice above."),
                    Field("entry", "Plan ahead at this entry price ($)", "number", "--entry", min=0, advanced=True,
                          help="Plan before the signal triggers, at the price you expect to buy."),
                    Field("flat_by", "Be out of the trade by (New York time)", "time", "--flat-by", advanced=True,
                          help="Default 15:55, just before the 4:00 PM close."),
                    _save("trader/plan.json"),
                ),
                extra=_stop_and_target,
                demo=NOW_1016 + ("--offline", f"{FIX}/trader-entry/TSLA-2026-10-19-5m.json"),
                demo_note="Plans from the demo entry signal (run the Entry Timer first).",
                sources=(YAHOO + ", only for an ATR stop",), reads=("entry.json", "config.json"), writes=("plan.json",),
                exit_codes={1: "The plan was refused (the reason is in the log). Usually: no triggered entry yet, or the stop is on the wrong side."},
            ),
            Action(
                id="show", label="Show my plan", args=("show",),
                summary="Prints the plan saved in trader/plan.json.",
                steps=("Read trader/plan.json and print it in plain numbers.",),
                demo=NOW_1016, reads=("plan.json",),
                exit_codes={1: "There is no plan yet, or it is for another day. Make one first."},
            ),
        ),
    ),
    Skill(
        id="timemachine", step=5, name="Time Machine", script="trader-timemachine/timemachine.py",
        tagline="Replays the rest of the day 10,000 times to show the odds.",
        plain=("Before risking money it asks: if today behaves like the last 60 days of this stock, how often "
               "would the target be hit first, and how often the stop? It rebuilds the rest of the day 10,000 "
               "times from real past candles, then checks how the same rule did on every real past day. It is a "
               "reality check, not a prediction."),
        output="timemachine.json", next="budget",
        actions=(
            Action(
                id="run", label="Run the replays", args=("run",),
                summary="Plays the rest of the trading day 10,000 times and counts how often the target or the stop comes first.",
                steps=(
                    "Read the plan (entry, stop, target) from trader/plan.json.",
                    "Download the stock's last 60 days of 5-minute candles and keep only complete trading days.",
                    "Turn every candle into a percentage move, filed by time of day.",
                    "One replay: start at the entry price, then for each 5-minute slot left in the day pick a real past move from about the same time of day, and see whether the stop or the target is touched first.",
                    "Repeat 10,000 times. The random draws use a fixed seed, so the same inputs always give the same numbers.",
                    "Check the same rule on every real past day (what actually happened), then give a one-line verdict.",
                ),
                fields=(
                    Field("replays", "Number of replays", "select", "--replays", "10000",
                          choices=(("1000", "1,000 (faster)"), ("10000", "10,000"), ("50000", "50,000 (slower)"))),
                    Field("seed", "Random seed", "int", "--seed", 19, min=0, advanced=True,
                          help="Same seed, same plan, same data: the same result. Change it to see how much the odds wobble."),
                    Field("until", "End each replay at (New York time)", "time", "--until", advanced=True,
                          help="Default 16:00, the close. Use your flat-by time (15:55) to match the plan."),
                    _save("trader/timemachine.json"),
                ),
                demo=("--offline", f"{FIX}/trader-timemachine/TSLA-60d5m.json.gz") + NOW_1016,
                demo_note="Uses TSLA's real 5-minute candles for the 60 days up to Oct 19 2026.",
                sources=(YAHOO + ": 60 days of 5-minute candles",), reads=("plan.json",), writes=("timemachine.json",),
                exit_codes={1: "It could not run (the reason is in the log). Usually: no plan yet, or not enough past data."},
            ),
            Action(
                id="chart", label="Text fan chart", args=("chart", "--from"),
                summary="Draws the saved replays as a text chart: the range where most replays ended up, bar by bar.",
                steps=("Read trader/timemachine.json and draw the spread of the replays in text.",),
                reads=("timemachine.json",),
                exit_codes={1: "No saved replay yet. Run the replays with \"Save the result\" ticked."},
            ),
        ),
    ),
    Skill(
        id="budget", step=6, name="Budget Manager", script="trader-budget/size.py",
        tagline="Works out how many shares fit your budget and your max loss.",
        plain=("The stop decides the size. If the stop is $5.86 below the entry and you never want to lose "
               "more than $50 on one trade, you can buy 8 shares (8 x $5.86 = $46.88). The Budget Manager "
               "checks four limits (max loss, position cap, max order, cash) and the smallest one wins. It "
               "writes a proposed order and places nothing."),
        output="orders.json", next="risk",
        actions=(
            Action(
                id="size", label="Size the trade",
                summary="Turns the plan into one proposed order with an exact number of shares.",
                steps=(
                    "Read the plan (entry, stop, target) and your rules from Settings (budget, max loss per trade, cash buffer...).",
                    "Max loss: your max loss per trade divided by the risk per share.",
                    "Position cap: the biggest share of your budget one stock may take, divided by the price.",
                    "Max order: the biggest single order, divided by the price.",
                    "Cash: the budget minus the cash you always keep aside, divided by the price.",
                    "Take the smallest of the four (whole shares) and write ONE bracket order (buy + stop-loss + take-profit) to trader/orders.json.",
                ),
                fields=(
                    Field("budget", "Use this budget instead of Settings ($)", "number", "--budget", min=1,
                          help="Leave empty to use the budget in Settings."),
                    Field("limit", "Use a limit order at the plan's entry price", "bool", "--limit", False,
                          help="A limit order never pays more than the entry. A market order (the default) buys at whatever the price is."),
                    _save("trader/orders.json"),
                ),
                demo=NOW_1016, demo_note="Sizes the demo plan with the budget in Settings ($5,000 and a $50 max loss by default).",
                reads=("plan.json", "config.json", "prices.json", "portfolio.json"), writes=("orders.json",),
                exit_codes={1: "No order: the trade does not fit your rules (the reason is in the log)."},
            ),
        ),
    ),
    Skill(
        id="risk", step=7, name="Risk Manager", script="trader-risk/check.py",
        tagline="Checks every order against your limits: PASS or BLOCK.",
        plain=("The last gate before an order can be shown to you for a yes. It checks the order against every "
               "limit you set: max loss per trade, daily loss limit, trades per day, reward vs risk, the "
               "trading-hours window, position size and cash. Any broken rule means BLOCK, with the reason."),
        output="state/risk.json", next="broker",
        actions=(
            Action(
                id="check", label="Check my orders",
                summary="Checks each proposed order in trader/orders.json and prints PASS or BLOCK with the reasons.",
                steps=(
                    "Read the proposed orders, your limits, your account (cash and holdings) and today's log of placed trades.",
                    "For each order: is there a stop? Does the loss at the stop fit your max loss per trade?",
                    "Is the reward at least as big as the risk? Does today's total risk still fit your daily loss limit?",
                    "Is it inside your trading-hours window, under your trades-per-day limit, and affordable without borrowing?",
                    "Print PASS or BLOCK per order and record the verdict, so the Order Executor only shows orders that passed.",
                ),
                fields=(
                    Field("record", "Record the verdicts", "bool", "--no-write", True, when_false=True,
                          help="The Order Executor only shows an order as READY if a PASS was recorded."),
                ),
                demo=NOW_1016,
                reads=("orders.json", "config.json", "portfolio.json", "prices.json", "state/broker.json"),
                writes=("state/risk.json",),
                exit_codes={1: "At least one order was BLOCKED (the reasons are in the log), or there were no orders to check."},
            ),
        ),
    ),
    Skill(
        id="broker", step=8, name="Order Executor", script="trader-broker/ticket.py",
        tagline="Shows the order ticket and records your yes. Never sends anything.",
        plain=("In the original skill pack, this is where Claude would send the order to a broker such as "
               "Alpaca, after your typed yes and a second click. This web app is not connected to any broker, "
               "so nothing is ever sent. You can see the ticket, record your yes or no, and log a paper trade "
               "by hand to practise the rest of the routine."),
        output="state/broker.json",
        actions=(
            Action(
                id="show", label="Show the tickets", args=("show",),
                summary="Shows each proposed order as a plain ticket, marked READY only if the Risk Manager passed it today.",
                steps=(
                    "Read the proposed orders and today's risk verdicts.",
                    "Match each order to its verdict by a fingerprint, so an order changed after the check is not READY.",
                    "Print the ticket: what is bought, the stop-loss, the take-profit and the most it can lose.",
                ),
                demo=NOW_1016, reads=("orders.json", "state/risk.json", "state/broker.json", "config.json"),
                exit_codes={1: "No ticket is READY. Run the Risk Manager first."},
            ),
            Action(
                id="approve", label="Say yes", args=("approve",),
                summary="Records your explicit yes for one order. A vague reply (\"sure\", \"yes to all\") is not accepted.",
                steps=(
                    "Check the order is READY (passed the Risk Manager today).",
                    "Check your reply is a clear yes for this one order.",
                    "Write your yes, word for word, to the log in trader/state/broker.json. Nothing is sent anywhere.",
                ),
                fields=(
                    Field("index", "Order number", "int", "--index", 1, min=1, required=True),
                    Field("reply", "Your reply", "text", "--reply", "yes", required=True,
                          help="Type it like you would answer \"Place this order?\""),
                ),
                demo=NOW_1016, reads=("orders.json", "state/risk.json"), writes=("state/broker.json",),
                exit_codes={1: "Not recorded: the order is not READY, or the reply was not a clear yes for it."},
            ),
            Action(
                id="decline", label="Say no", args=("decline",),
                summary="Records that you declined an order.",
                steps=("Write your no for this order to the log in trader/state/broker.json.",),
                fields=(Field("index", "Order number", "int", "--index", 1, min=1, required=True),),
                demo=NOW_1016, reads=("orders.json",), writes=("state/broker.json",),
            ),
            Action(
                id="result", label="Log what happened", args=("result",),
                summary="If you placed the order yourself at a broker (or on paper), record what happened so the daily limits stay right.",
                steps=(
                    "Find the approved order in the log.",
                    "Record whether it was placed, denied or failed, and the fill if there was one.",
                    "A placed order counts toward today's trade count and daily loss limit in the Risk Manager; the shares go into trader/portfolio.json.",
                ),
                fields=(
                    Field("index", "Order number", "int", "--index", 1, min=1, required=True),
                    Field("status", "What happened", "select", "--status", "placed",
                          choices=(("placed", "Placed"), ("denied", "I changed my mind"), ("failed", "It failed"))),
                    Field("filled_qty", "Shares filled", "int", "--filled-qty", min=0),
                    Field("filled_price", "Fill price ($)", "number", "--filled-price", min=0),
                    Field("note", "Note", "text", "--note", "logged by hand in the web app, paper only"),
                ),
                demo=NOW_1016, reads=("state/broker.json",), writes=("state/broker.json", "portfolio.json"),
            ),
            Action(
                id="fill", label="Log a fill", args=("fill",),
                summary="Records a buy or sell that filled (for example the stop or the target), updating your paper holdings.",
                steps=("Add the trade to trader/portfolio.json (cash and shares) and to the log.",),
                fields=(
                    Field("symbol", "Stock", "ticker", "--symbol", "TSLA", required=True),
                    Field("side", "Side", "select", "--side", "sell", choices=(("sell", "Sell"), ("buy", "Buy"))),
                    Field("qty", "Shares", "int", "--qty", 8, min=1, required=True),
                    Field("price", "Price ($)", "number", "--price", 370.04, min=0, required=True),
                ),
                demo=("--now", f"{DEMO_DAY} 11:30"), writes=("portfolio.json", "state/broker.json"),
            ),
            Action(
                id="flatten", label="Close a position", args=("flatten",),
                summary="Builds the sell ticket that closes what you hold in a stock by the flat-by time.",
                steps=(
                    "Look up how many shares you hold (from trader/portfolio.json, or the number you give).",
                    "Write a market sell order for them to trader/orders.json. Run the Risk Manager and say yes, as for a buy.",
                ),
                fields=(
                    Field("symbol", "Stock", "ticker", "--symbol", "TSLA", required=True),
                    Field("qty", "Shares (optional)", "int", "--qty", min=1, help="Leave empty to use your paper holdings."),
                ),
                demo=("--now", f"{DEMO_DAY} 15:55"), reads=("portfolio.json", "plan.json"), writes=("orders.json",),
            ),
            Action(
                id="log", label="Today's log", args=("log",),
                summary="Lists every yes, no, placed order and fill recorded today.",
                steps=("Read trader/state/broker.json and print today's entries.",),
                fields=(Field("all", "Every day, not just today", "bool", "--all", False),),
                demo=NOW_1016, reads=("state/broker.json",),
            ),
        ),
    ),
    Skill(
        id="alerts", name="Price Alerts", script="trader-alerts/alerts.py",
        tagline="Rings when a price, your stop or a time is reached.",
        plain=("Nobody can stare at a chart all day. You set alerts (a price above or below a level, your stop, "
               "your target, \"time to close\") and each check rings any alert that was reached, once. It also "
               "knows the NYSE's opening hours and holidays, and fetches delayed quotes."),
        output="alerts.json",
        actions=(
            Action(
                id="clock", label="Is the market open?", args=("clock",),
                summary="Says whether the New York Stock Exchange is open right now and when it next opens.",
                steps=("Work out the time in New York (summer time included) and check it against NYSE hours, holidays and early closes.",),
                fields=(_demo_clock((("09:00", "9:00 AM"), ("10:15", "10:15 AM"), ("16:30", "4:30 PM")), "10:15", "Demo: pick a moment on Oct 19 2026."),),
                exit_codes={1: "The market is closed at that moment."},
            ),
            Action(
                id="quote", label="Get a price", args=("quote",),
                summary="Fetches the latest (delayed) price of one or more stocks.",
                steps=(
                    "Download the latest quote for each stock from Yahoo Finance, half a second apart.",
                    "Print the price and the time it is from, and save it to trader/prices.json for sizing and the risk check.",
                ),
                fields=(
                    Field("symbols", "Stocks", "tickers", None, "TSLA", required=True,
                          help="Demo mode has recorded quotes for TSLA, AAPL, AXP, BAC, GOOGL and KO."),
                    Field("write", "Save to trader/prices.json", "bool", "--write", True),
                ),
                demo=("--offline", f"{FIX}/trader-alerts"),
                sources=(YAHOO,), writes=("prices.json",),
            ),
            Action(
                id="from_plan", label="Alerts from my plan", args=("add", "--from-plan"),
                summary="Adds three alerts in one go: your stop, your target and \"time to close\" at your flat-by time.",
                steps=("Read the stop, the target and the flat-by time from trader/plan.json.",
                       "Add three alerts for the plan's day to trader/alerts.json."),
                reads=("plan.json", "config.json"), writes=("alerts.json",),
                exit_codes={1: "No plan to read. Make one with the Exit Planner first."},
            ),
            Action(
                id="price", label="Price alert", args=("add",),
                summary="Rings when a stock goes above or below a price.",
                steps=("Add the rule to trader/alerts.json. A check rings it once when the price gets there.",),
                fields=(
                    Field("symbol", "Stock", "ticker", "--symbol", "TSLA", required=True),
                    Field("direction", "Ring when the price is", "select", None, "above", arg=False,
                          choices=(("above", "At or above"), ("below", "At or below"))),
                    Field("price", "Price ($)", "number", arg=False, required=True, min=0),
                ),
                extra=_price_alert, writes=("alerts.json",),
            ),
            Action(
                id="check", label="Check my alerts", args=("check",),
                summary="Fetches the prices for today's alerts and rings any that were reached.",
                steps=(
                    "Read your alerts and keep the ones for today.",
                    "Fetch the latest delayed quote for each stock involved.",
                    "Ring each alert that was reached (once only), and save the prices to trader/prices.json.",
                ),
                fields=(_demo_clock((("10:53", "10:53 AM"), ("15:56", "3:56 PM")), "15:56"),),
                demo=("--offline", f"{FIX}/trader-alerts"),
                sources=(YAHOO,), reads=("alerts.json", "state/alerts.json"), writes=("state/alerts.json", "prices.json"),
                exit_codes={1: "Nothing rang."},
            ),
            Action(
                id="list", label="My alerts", args=("list",),
                summary="Lists your alerts and whether each has already rung.",
                steps=("Read trader/alerts.json and trader/state/alerts.json.",),
                reads=("alerts.json", "state/alerts.json"),
            ),
        ),
    ),
    Skill(
        id="analyst", name="Earnings Analyst", script="trader-analyst/facts.py",
        tagline="Reads a company's official numbers and says what changed.",
        plain=("Earnings move stocks more than anything else, and press releases put the best number first. "
               "This skill reads the numbers the company itself filed with the SEC: revenue, profit margins, "
               "net income and earnings per share, quarter by quarter, each compared with the same quarter a "
               "year earlier."),
        output="metrics.json",
        actions=(
            Action(
                id="facts", label="Read the numbers",
                summary="Builds a quarter-by-quarter table of revenue, margins and earnings per share from SEC filings.",
                steps=(
                    "Look up the company's SEC ID (its CIK) from its ticker.",
                    "Download every number the company tagged in its 10-Q and 10-K reports (SEC \"XBRL company facts\").",
                    "Line the quarters up. The 4th quarter is worked out as the full year minus the first three, and marked \"derived\".",
                    "Compare each quarter with the same quarter a year earlier, and add up the last four quarters (TTM).",
                    "Find the latest quarterly report and earnings press release, and flag anything unusual.",
                ),
                fields=(
                    Field("tickers", "Companies", "tickers", None, "AAPL", required=True,
                          help="Demo mode has recorded filings for AAPL and KO."),
                    Field("quarters", "Quarters to show", "int", "--quarters", 6, min=1, max=20),
                    Field("filings", "Find the latest report and press release", "bool", "--no-filings", True,
                          when_false=True),
                    Field("metrics", "Save a summary row to trader/metrics.json", "bool", "--metrics", False,
                          fmt="trader/metrics.json"),
                ),
                demo=("--offline", f"{FIX}/trader-analyst"),
                demo_note="Uses SEC data recorded on Oct 13 2026.",
                sources=("SEC EDGAR company facts and filings (sec.gov)",), reads=("config.json",),
                writes=("metrics.json",), needs_sec=True,
            ),
        ),
    ),
    Skill(
        id="pelosi", name="Pelosi Tracker", script="trader-pelosi/ptr.py",
        tagline="Reads the stock trades members of Congress must disclose.",
        plain=("By law (the STOCK Act), members of the US House must publicly report their stock trades within "
               "45 days. The House Clerk posts each report. This skill reads the official index, spots new "
               "reports and turns them into clean rows. These are public filings, weeks old by the time anyone "
               "sees them: not inside information."),
        output="state/pelosi.json",
        actions=(
            Action(
                id="index", label="List the filings", args=("index",),
                summary="Lists the trade reports a member of Congress (or everyone) filed this year.",
                steps=(
                    "Download the House Clerk's yearly index of financial disclosures (a zip file).",
                    "Keep the Periodic Transaction Reports (PTRs: the trade reports), for the member you name.",
                    "Print each with its filing date and a link to the official PDF.",
                ),
                fields=(
                    Field("member", "Member of Congress", "text", "--member", "pelosi",
                          help="A last name, or \"First Last\". Leave empty for everyone."),
                    Field("since", "Filed on or after", "date", "--since"),
                    Field("year", "Year", "int", "--year", min=2012, max=2100, advanced=True),
                    Field("limit", "Show at most", "int", "--limit", 20, min=1, max=500),
                ),
                demo=("--offline", f"{FIX}/trader-pelosi/2026FD.zip", "--year", "2026"),
                demo_note="Uses a trimmed copy of the 2026 House index.",
                sources=("House Clerk financial disclosures (disclosures-clerk.house.gov)",),
            ),
            Action(
                id="new", label="Anything new?", args=("new",),
                summary="Shows only the reports filed since the last check (the first check shows the last 45 days).",
                steps=(
                    "Download the yearly index and compare it with the reports already shown (trader/state/pelosi.json).",
                    "Print only the new ones, and remember them so each one appears once.",
                    "Optionally download each new report and read its rows.",
                ),
                fields=(
                    Field("member", "Member of Congress", "text", "--member", "pelosi"),
                    Field("read", "Download and read each new report", "bool", "--read", False,
                          help="Reading the PDF needs the free pdftotext tool installed. Without it the PDF is saved for you to open."),
                ),
                demo=("--offline", f"{FIX}/trader-pelosi/2026FD.zip", "--year", "2026", "--today", "2026-10-13"),
                sources=("House Clerk financial disclosures (disclosures-clerk.house.gov)",),
                reads=("state/pelosi.json", "portfolio.json"), writes=("state/pelosi.json",),
                exit_codes={1: "Nothing new since the last check."},
            ),
            Action(
                id="fetch", label="Read one report", args=("fetch",),
                summary="Downloads one trade report (by its document number) and turns it into rows: who, what, buy or sell, amount range, dates.",
                steps=(
                    "Download the report PDF from the House Clerk's site into trader/state/ptr-pdfs/.",
                    "Turn the PDF into text with pdftotext (if installed).",
                    "Read each trade: owner (the member, spouse or child), stock, buy or sell, options details, trade date, amount range and how many days it took to report.",
                ),
                fields=(
                    Field("doc_id", "Document number", "text", None, "20035143", required=True,
                          help="The \"doc\" number from \"List the filings\"."),
                ),
                modes=("live",),
                sources=("House Clerk financial disclosures (disclosures-clerk.house.gov)",),
                writes=("state/ptr-pdfs/",),
            ),
            Action(
                id="parse", label="Read a recorded report", args=("parse", f"{FIX}/trader-pelosi/ptr-20035143.txt", "--filed", "2026-08-21"),
                summary="Reads the recorded text of report 20035143 (filed Aug 21 2026) into rows.",
                steps=(
                    "Read the text of the report.",
                    "Pick out each trade: owner, stock, buy or sell, options details, trade date, amount range and reporting delay.",
                ),
                modes=("demo",), demo_note="Demo only: the real text of Nancy Pelosi's report 20035143.",
            ),
        ),
    ),
)

SKILLS_BY_ID = {s.id: s for s in SKILLS}

# Phrases the skills print, explained for a beginner. (regex, tone, title, explanation)
EXPLAINERS = (
    (r"\bTRIGGERED\b", "good", "The entry signal fired",
     "A finished candle closed above the line the setup was watching. A trader following this rule would buy now. Nothing was bought."),
    (r"\bWAITING\b", "info", "Not yet",
     "The price has not closed above the line yet. The log says how far away it is."),
    (r"\bEXPIRED\b|too late|after the entry cutoff", "warn", "Too late for today",
     "The rule allows no new entries this late in the day (default: after 3:30 PM New York time)."),
    (r"range is still forming|before 9:45|still forming", "info", "The opening range is still forming",
     "The first 15 minutes are not over yet, so there is no range to break."),
    (r"NYSE closed|market is closed|not open yet", "info", "The market is closed",
     "US stocks trade 9:30 AM to 4:00 PM New York time on weekdays. Outside those hours the live skills have nothing new to read. Try Demo mode."),
    (r"\bPASS\b", "good", "PASS",
     "This order fits every one of your limits. It may now be shown to you for a yes. A PASS is a rules check, not a recommendation."),
    (r"\bBLOCK\b", "bad", "BLOCK",
     "This order breaks at least one of your rules (the reason is under it). It will not be shown for a yes. Fix the plan or the size, or skip the trade."),
    (r"\bREADY\b", "good", "Ready for your decision",
     "The Risk Manager passed this exact order today. In this web app nothing is ever sent to a broker."),
    (r"NOT READY", "warn", "Not ready",
     "This order has no PASS from the Risk Manager today (or it changed after the check). Run the Risk Manager."),
    (r"Recorded your yes", "good", "Your yes is logged",
     "Logged in trader/state/broker.json. In the original skill pack Claude would now ask the broker, with a second confirmation. Here nothing is sent."),
    (r"Not recorded", "warn", "Your reply was not taken as a yes",
     "Only a clear yes for this one order counts. \"sure\", \"ok\" or \"yes to all\" do not."),
    (r"\bMOVING\b", "warn", "Big move today",
     "This stock is 3% or more away from yesterday's close. Look for the reason before trading it."),
    (r"Close to a coin flip|Close to break-even", "warn", "No real edge",
     "In the replays the target and the stop came first about equally often, for this size of target. Treat it as a coin flip, not an opportunity."),
    (r"Leans toward the target|Strongly toward the target", "good", "The replays favour the target",
     "In past days like this one, the target was reached first more often than the target size needs to break even. Still a simulation, not a promise."),
    (r"Leans toward the stop|Strongly toward the stop", "bad", "The replays favour the stop",
     "In past days like this one, the stop was hit first more often than the target size can afford. The odds are against this plan."),
    (r"<- binds", "info", "Which limit decided the size",
     "Of the four limits, the one marked \"binds\" gave the fewest shares, so that is the size."),
    (r"\bPARTIAL\b", "warn", "Partial scan",
     "Not every candidate was checked in detail (only the most traded ones). Matches may be missing."),
    (r"\bALERT\b", "warn", "An alert rang",
     "One of your alert rules was reached. An alert is information, never an order."),
    (r"Nothing hit|Nothing rang", "info", "No alert rang", "None of today's alert rules was reached at this check."),
    (r"Nothing new", "info", "Nothing new", "Everything found was already shown at an earlier check."),
    (r"NEW Periodic Transaction Report", "info", "A new trade report",
     "A member of Congress filed a report of trades. It is public and usually weeks old: a reason to look at a chart, not a signal."),
    (r"derived", "info", "Derived quarter",
     "Companies do not file a 4th-quarter report. The 4th quarter is the yearly report minus the three quarters inside it."),
    (r"NOTE: SEC's XBRL facts stop", "warn", "The SEC data lags",
     "A newer quarterly report exists than the SEC's number feed has caught up with. Read the report itself for the latest quarter."),
    (r"net income is above operating income|above operating income", "info", "One-off gains inside the profit",
     "Profit is higher than what the business itself earned, so gains from outside the business (investments, tax items) are included."),
    (r"Wrote trader/|Wrote \d+ proposed", "info", "Result saved",
     "The result was saved in the trader/ folder, where the next skill in the chain will read it. Open it under \"Files saved\"."),
    (r"no trader/universe\.txt yet|run `scan\.py universe` first", "warn", "The stock list is missing",
     "Scanning the whole market needs the list of US stocks first. Run \"All US stocks\", or type a few tickers instead."),
    (r"[Nn]o sec_user_agent|SEC User-Agent|without a User-Agent|filings skipped", "warn", "Your SEC identity is missing",
     "The SEC asks every visitor for a name and email. Add yours in Settings to include SEC filings."),
    (r"pdftotext", "info", "Reading the PDF",
     "Turning the report PDF into rows needs the free pdftotext tool (part of Poppler). Without it the PDF is saved and you can open it yourself."),
)

GLOSSARY = {
    "Ticker": "The short code of a stock on the exchange, e.g. TSLA for Tesla, AAPL for Apple.",
    "Candle (bar)": "The price over one slice of time, e.g. 5 minutes: where it opened, its high, its low and where it closed.",
    "Opening range": "The highest and lowest price in the first 15 minutes after the 9:30 AM New York open.",
    "Breakout": "A candle that closes above a level the price had not got past before, such as the opening-range high.",
    "Watchlist": "The short list of stocks the scanner found, saved for the next skills.",
    "Stop (stop-loss)": "A price below your entry where you sell to cap the loss if the idea was wrong. In a fast market it can fill lower.",
    "Target (take-profit)": "A price above your entry where you sell to take the profit.",
    "R (risk unit)": "Entry minus stop: what one share loses if the stop is hit. A 2R target aims to make twice that.",
    "Reward:risk": "How far the target is from the entry, divided by how far the stop is. 1.0 means the same distance.",
    "Flat by": "The time you are out of the trade, win or lose, so nothing is held overnight. Default 3:55 PM New York time.",
    "Bracket order": "One buy order with its stop-loss and take-profit attached. When one of them fills, the broker cancels the other.",
    "Market order": "Buy or sell now at whatever the current price is.",
    "Limit order": "Buy or sell only at your price or better.",
    "Paper trading": "Practice trading with pretend money on a real broker's simulator.",
    "Max loss per trade": "The most you allow one trade to lose if the stop fills at the stop price. It decides how many shares you buy.",
    "Daily loss limit": "The most all of today's trades together may lose at their stops. After that, no new trades today.",
    "Cash buffer": "The share of your budget that always stays in cash.",
    "ATR": "Average true range: how much the price typically moves in one candle. Used to set a stop that fits the stock's normal wiggle.",
    "RSI": "Relative strength index, 0 to 100. Under 30 is called oversold: the price fell fast recently.",
    "20-day average": "The average closing price of the last 20 trading days, a common trend line.",
    "Bull flag": "A strong rise followed by a few quiet days in a tight range.",
    "Replay (Monte Carlo)": "Simulating many possible versions of the rest of the day by drawing real past price moves at random.",
    "Seed": "The starting number of the random draws. Same seed, same inputs: exactly the same result.",
    "8-K": "A report a US company must file with the SEC within days of an important event: earnings, a new CEO, a deal...",
    "10-Q / 10-K": "A company's quarterly (10-Q) and yearly (10-K) financial reports filed with the SEC.",
    "SEC EDGAR": "The US Securities and Exchange Commission's public database of company filings.",
    "EPS": "Earnings per share: the company's profit divided by its number of shares.",
    "Margin": "Profit as a share of revenue. Gross: after the cost of the goods. Operating: after running the business. Net: after everything.",
    "TTM": "Trailing twelve months: the total of the last four quarters.",
    "YoY": "Year on year: compared with the same quarter one year earlier.",
    "PTR": "Periodic Transaction Report: the trade report members of Congress must file within 45 days of a trade.",
    "NYSE": "The New York Stock Exchange. Regular hours are 9:30 AM to 4:00 PM New York time on weekdays, except holidays.",
}

# Your rules, saved in trader/config.json and read by the skills.
SETTINGS = (
    Field("budget", "Budget for day trading ($)", "number", default=5000, min=1,
          help="Only money you can afford to lose."),
    Field("max_loss_per_trade_usd", "Max loss per trade ($)", "number", default=50, min=1,
          help="The most one trade may lose if the stop is hit. This decides how many shares you buy."),
    Field("max_daily_loss_usd", "Daily loss limit ($)", "number", default=150, min=1,
          help="When today's trades together could lose this much, no new trades today."),
    Field("max_trades_per_day", "Trades per day", "int", default=3, min=1, max=100),
    Field("cash_buffer_pct", "Always keep in cash (%)", "number", default=10, min=0, max=100),
    Field("max_position_pct", "Biggest position (% of budget)", "number", default=75, min=1, max=100),
    Field("max_order_usd", "Biggest single order ($)", "number", default=4000, min=1),
    Field("min_reward_risk", "Minimum reward:risk", "number", default=1.0, min=0,
          help="1.0 means the target must be at least as far above the entry as the stop is below it."),
    Field("no_entries_before", "No new trades before (New York time)", "time", default="09:45"),
    Field("no_entries_after", "No new trades after (New York time)", "time", default="15:30"),
    Field("flat_by", "Be out of every trade by (New York time)", "time", default="15:55"),
    Field("blocked", "Never trade these stocks", "tickers", placeholder="e.g. GME, AMC"),
    Field("sec_user_agent", "Your name and email, for the SEC", "text", placeholder="Jane Doe jane@example.com",
          help="The SEC asks everyone who downloads filings to say who they are. Only sent to sec.gov, "
               "only by the News Monitor and the Earnings Analyst in live mode."),
)

# How each journey step is marked done: the file it leaves in trader/.
JOURNEY = tuple((s.id, s.step, s.name, s.output) for s in SKILLS if s.step)


def to_json():
    """The catalog as plain data for the page (callables left out)."""
    def action(a):
        d = asdict(a)
        d.pop("extra")
        d["exit_codes"] = {str(k): v for k, v in a.exit_codes.items()}
        d["fields"] = [asdict(f) for f in a.fields]
        d.pop("demo")
        d.pop("args")
        return d

    return {
        "skills": [
            {**{k: v for k, v in asdict(s).items() if k != "actions"},
             "actions": [action(a) for a in s.actions]}
            for s in SKILLS
        ],
        "explainers": [{"pattern": p, "tone": t, "title": ti, "text": tx} for p, t, ti, tx in EXPLAINERS],
        "glossary": GLOSSARY,
        "settings": [asdict(f) for f in SETTINGS],
    }
