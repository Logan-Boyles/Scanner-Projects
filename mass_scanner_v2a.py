import asyncio
import os
import config
from data_collection_functions_a import scan_chart_candles, send_to_discord_new, crop_and_save_image, run_scanner
from ms_engine_a import SetupEngine

current_dir = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.join(current_dir, "tradingview_session")

# Execution Flags
SHOW_IMAGE = False  # Shows the cv2 image for debugging
PING_DISCORD = True  # Posts the results in Discord
ENABLE_ALGO = False  # Enables the algo scanner
ALGO_DEBUG = False  # Shows the S/R points calculated on the chart. Not implemented yet in v2

# MAJOR ADDITIONS
# TODO Candle Patterns - these are like half implemented is fineeeee the imports are there on the class I just need to add like 5 if statements
# U&R and False Breakouts do Exist but are probably insanely difficult to code and unreliable

# MINOR ADDITIONS
# TODO If an active make lookback 3 else 2. Probably check computer time for that.

if __name__ == '__main__':
    engine = SetupEngine(config.RUN_PROFILE)
    algo_engine = SetupEngine(config.ALGO_PROFILE)

    msg = ""
    algo_msg = ''
    SCAN_TYPE = 4

    if SCAN_TYPE == 1:
        stocks = config.WATCHLIST
    elif SCAN_TYPE == 2:
        stocks = config.ARCHIVED_WL
    elif SCAN_TYPE == 3:
        stocks = config.WATCHLIST + config.ARCHIVED_WL
    elif SCAN_TYPE == 4:
        stocks = config.DEBUG_WL

    count = 0

    for ticker in stocks:
        count += 1
        bar_length = 20
        scan_time = 5.11 * (len(stocks) - count + 1)
        progress = count / len(stocks)
        filled_len = int(bar_length * progress)
        bar = '█' * filled_len + '-' * (bar_length - filled_len)
        print(
            f'\rScanning {ticker.upper():<6} |[{bar}] {count}/{len(stocks)} | {int(scan_time // 60)} Minutes Remaining',
            end='', flush=True)

        # Ingest chart layout
        CHART_URL = f"https://www.tradingview.com/chart/{config.TV_CHART_ID}/?symbol={ticker}"
        asyncio.run(run_scanner(CHART_URL, "mass_scanner.png"))
        crop_and_save_image("mass_scanner.png")

        # Run the scan using configured technical indicators
        history = scan_chart_candles(
            "cropped_mass_scanner.png",
            emas=config.MY_EMAS,
            lines=config.MY_LINES,
            ENABLE_ALGO=ENABLE_ALGO,
            SHOW_IMAGE=SHOW_IMAGE
        )

        engine.process_ticker(ticker, history)
        if ENABLE_ALGO:
            algo_engine.process_ticker(ticker, history)

    msg = engine.generate_report()
    print(msg)
    print("\n\n")

    if PING_DISCORD:
        send_to_discord_new("**LogaVision Results:**", msg, 'config.txt')

    if ENABLE_ALGO:
        algo_msg = algo_engine.generate_report()
        print(algo_msg)
        if PING_DISCORD:
            send_to_discord_new("**LogaVision Algo Results:**", algo_msg, 'config.txt')