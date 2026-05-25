from data_collection_functions_a import scan_chart_candles, crop_and_save_image, run_scanner, send_to_discord_new
import time
import asyncio
import config
from candle_momentum_logic_a import (get_specific_candle_type, get_algorithmic_momentum, calculate_atr,
                                          get_chop_density, is_ribbon_fanning,
                                          ensemble_chop_oscillator)
from day_functions_a import (generate_active_zones, draw_debug_zones, find_setup, create_alert,
                             filter_new_session, parse_indicator_touches, check_zone_taps)

START_MSG = "🚨 **Day Trade Setup Detected!**🚨"
prev_messageID = -1

"""
Needed Fixes
Need to add a check to make sure its actually a uptrend tap and not a recent breakdown just closing slightly below an indicator - Lookback var
Zone overlapping exists, probably can simplify that
More strict on the tolerance especially for not reaching the zone. Allow over but not under
Fix whatever is causing the scalp signal
"""

if __name__ == '__main__':
    # TODO trend indicators
    # TODO EMA ribbon trends
    # TODO remove the conflicting signals of structure setup
    # TODO write comments and reorganize this file seeing I am sharing it now.
    # TODO fix the structure bug
    # TODO still need to make a small candle oscillator that works

    SHOW_ZONES = False
    CHART_URL = f"https://www.tradingview.com/chart/{config.DAY_TV_CHART_ID}/?symbol={config.DAY_TICKER}"
    prev_messageID = -1


    while True:
        vwap_relation = "None"
        asyncio.run(run_scanner(CHART_URL, "day_chart.png", HEADLESS=True))
        crop_and_save_image("day_chart.png")

        # Configured EMA and VWAP mappings
        raw_history = scan_chart_candles(
            "cropped_day_chart.png",
            emas=config.DAY_EMAS,
            SHOW_IMAGE=False
        )


        day_history = filter_new_session(raw_history, vertical_gap_threshold=config.SESSION_GAP_THRESH)
        print(is_ribbon_fanning(day_history[-1]))
        micro_zones = generate_active_zones(day_history, window=config.MICRO_ZONE_WINDOW,
                                            tolerance=config.ZONE_TOLERANCE)
        macro_zones = generate_active_zones(day_history, window=config.MACRO_ZONE_WINDOW,
                                            tolerance=config.ZONE_TOLERANCE)

        if SHOW_ZONES:
            draw_debug_zones("cropped_day_chart.png", micro_zones, macro_zones)

        latest = day_history[-1]
        oscillator = get_algorithmic_momentum(day_history, config.OSCILLATOR_LOOKBACK)
        cType = get_specific_candle_type(latest)
        atr = calculate_atr(day_history)

        try:
            if latest['vwap_upper'] > latest['close']:
                vwap_relation = "Above"
            if latest['vwap_lower'] < latest['close']:
                vwap_relation = "Below"
            if latest['vwap_upper'] < latest['close'] < latest['vwap_lower']:
                vwap_relation = "Inside"

        except TypeError:
            try:
                prev = day_history[-2]
                if prev['vwap_upper'] > prev['close']:
                    vwap_relation = "Above"
                if prev['vwap_lower'] < prev['close']:
                    vwap_relation = "Below"
                if prev['vwap_upper'] < prev['close'] < prev['vwap_lower']:
                    vwap_relation = "Inside"
            except TypeError:
                # There is like surely a better way to do this
                print("Failed to read VWAP context. Skipping cycle.")
                continue

        is_setup, touches = find_setup(day_history, tolerance=config.SETUP_TOLERANCE)
        line_flags = parse_indicator_touches(touches)

        is_micro_tap, micro_dir = check_zone_taps(day_history, micro_zones, lookback=config.TAP_LOOKBACK,
                                                    tap_tolerance=config.TAP_TOLERANCE)
        is_macro_tap, macro_dir = check_zone_taps(day_history, macro_zones, lookback=config.TAP_LOOKBACK,
                                                      tap_tolerance=config.TAP_TOLERANCE)

        macro_flags = {
            'support': is_macro_tap and macro_dir == 'support',
            'resistance': is_macro_tap and macro_dir == 'resistance'
        }

        micro_flags = {
            'support': is_micro_tap and micro_dir == 'support',
            'resistance': is_micro_tap and micro_dir == 'resistance'
        }

        # Confluence and Chop Metrics
        oscillator = get_algorithmic_momentum(day_history, config.OSCILLATOR_LOOKBACK)
        consol = get_chop_density(day_history)
        echop = ensemble_chop_oscillator(day_history)

        print("Density:", consol)
        print("Oscillator:", oscillator)
        print("Echop:", echop)

        alert_message, msg_id = create_alert(vwap_relation, macro_flags, micro_flags, line_flags, oscillator,
                                             day_history)

        if alert_message != "None" and msg_id != prev_messageID:
            send_to_discord_new(START_MSG, alert_message, "day_config.txt")
            prev_messageID = msg_id
            time.sleep(config.ALERT_COOLDOWN)
            continue

        time.sleep(config.SCAN_INTERVAL)