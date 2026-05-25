import cv2
import config
from candle_patterns_and_momentum import (get_specific_candle_type, get_algorithmic_momentum, calculate_atr,
                                          get_chop_density, is_ribbon_fanning,
                                          ensemble_chop_oscillator, density_ensemble_chop_oscillator)


def find_setup(history, tolerance=5, strict_tap=True):
    """
    Scans the most recent price action for precise indicator touches.
    """
    if len(history) < 2:
        return False, []

    latest = history[-1]
    prev = history[-2]

    c_open = latest.get('open')
    c_high = latest.get('high')
    c_low = latest.get('low')

    indicators = ['ema_short', 'ema_mid', 'vwap_upper', 'vwap_lower', 'vwap_center']
    taps = []

    for ind in indicators:
        ind_y = latest.get(ind)
        prev_ind_y = prev.get(ind)

        if ind_y is None or prev_ind_y is None:
            continue

        prev_crossed_down = prev.get('open') < prev_ind_y and prev.get('close') > prev_ind_y
        prev_crossed_up = prev.get('open') > prev_ind_y and prev.get('close') < prev_ind_y

        if c_open < ind_y:
            if abs(c_low - ind_y) <= tolerance:
                if strict_tap and prev_crossed_up:
                    continue
                taps.append((ind, 'From Above'))

        elif c_open > ind_y:
            if abs(c_high - ind_y) <= tolerance:
                if strict_tap and prev_crossed_down:
                    continue
                taps.append((ind, 'From Below'))

        else:
            taps.append((ind, 'Opened On Line'))

    if taps:
        return True, taps

    return False, []


def generate_active_zones(day_history, window=5, enable_lookback=True, tolerance=2):
    """
    Scans a chronological list of candles to identify structural pivots.
    Returns dictionaries of active support and resistance zones.
    """
    zones = {'resistance': [], 'support': []}

    for i in range(0, max(0, len(day_history) - 2)):
        current = day_history[i]

        left_bound = max(0, i - window) if enable_lookback else i
        right_bound = min(len(day_history), i + window + 1)
        subset = day_history[left_bound:right_bound]

        min_y_in_subset = min(c['high'] for c in subset)
        if abs(current['high'] - min_y_in_subset) <= tolerance:
            top = current['high']

            highest_bodies = [min(c['open'], c['close']) for c in subset]
            bottom = min(highest_bodies)

            if bottom < top:
                bottom = max(current['open'], current['close'])

            if abs(bottom - top) < 2:
                bottom = top + 2

            if not any(abs(z['top'] - top) <= tolerance for z in zones['resistance']):
                zones['resistance'].append({'top': top, 'bottom': bottom, 'index': i})

        max_y_in_subset = max(c['low'] for c in subset)
        if abs(current['low'] - max_y_in_subset) <= tolerance:
            bottom = current['low']

            lowest_bodies = [max(c['open'], c['close']) for c in subset]
            top = max(lowest_bodies)

            if top > bottom:
                top = min(current['open'], current['close'])

            if abs(bottom - top) < 2:
                top = bottom - 2
            if not any(abs(z['bottom'] - bottom) <= tolerance for z in zones['support']):
                zones['support'].append({'top': top, 'bottom': bottom, 'index': i})

    active_zones = {'resistance': [], 'support': []}

    for z_type in ['resistance', 'support']:
        for zone in zones[z_type]:
            is_broken = False

            for c in day_history[zone['index'] + 1:]:
                if z_type == 'resistance' and c['close'] < zone['top']:
                    is_broken = True
                    break
                if z_type == 'support' and c['close'] > zone['bottom']:
                    is_broken = True
                    break

            if not is_broken:
                active_zones[z_type].append(zone)

    return active_zones


def draw_debug_zones(image_path, micro_zones, macro_zones):
    """Overlays the calculated zones onto the original chart image."""
    img = cv2.imread(image_path)
    if img is None: return

    for zone in micro_zones.get('support', []):
        cv2.rectangle(img, (0, zone['top']), (img.shape[1], zone['bottom']), (255, 100, 0), 1)
    for zone in micro_zones.get('resistance', []):
        cv2.rectangle(img, (0, zone['top']), (img.shape[1], zone['bottom']), (255, 200, 0), 1)

    for zone in macro_zones.get('support', []):
        cv2.rectangle(img, (0, zone['top']), (img.shape[1], zone['bottom']), (150, 0, 150), 2)
    for zone in macro_zones.get('resistance', []):
        cv2.rectangle(img, (0, zone['top']), (img.shape[1], zone['bottom']), (200, 0, 200), 2)

    cv2.imshow("Zone Debug Viewer", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def check_zone_taps(day_history, zones, lookback=1, tap_tolerance=3):
    """
    Scans the last 'lookback' candles for zone interactions.
    Determines if it was a Support or Resistance test strictly based on the candle's Open price.
    Returns: (bool: tapped_zone, str: tap_direction)
    """

    target_candles = day_history[-lookback:] if lookback > 0 else []
    target_candles.reverse()

    all_zones = zones.get('resistance', []) + zones.get('support', [])

    for candle in target_candles:
        for zone in all_zones:

            pad_top = zone['top'] - tap_tolerance
            pad_bot = zone['bottom'] + tap_tolerance

            if candle['low'] >= pad_top and candle['high'] <= pad_bot:

                if candle['open'] < zone['top']:
                    return True, 'support'

                elif candle['open'] > zone['bottom']:
                    return True, 'resistance'

                else:
                    if candle['close'] < candle['open']:
                        return True, 'support'
                    else:
                        return True, 'resistance'

    return False, None


def parse_indicator_touches(touches):
    """
    Translates a list of tuples into a dictionary of Boolean flags.
    """
    flags = {
        'EMA_SHORT_FROM_BELOW': False, 'EMA_SHORT_FROM_ABOVE': False,
        'EMA_MID_FROM_BELOW': False, 'EMA_MID_FROM_ABOVE': False,
        'VWAP_UPPER_FROM_BELOW': False, 'VWAP_UPPER_FROM_ABOVE': False,
        'VWAP_LOWER_FROM_BELOW': False, 'VWAP_LOWER_FROM_ABOVE': False,
        'VWAP_CENTER_FROM_BELOW': False, 'VWAP_CENTER_FROM_ABOVE': False,
    }

    for indicator, direction in touches:
        clean_key = f"{indicator.upper()}_{direction.replace(' ', '_').upper()}"
        if clean_key in flags:
            flags[clean_key] = True

    return flags


def format_discord_alert(tier, is_bull, is_scalp, triggers, notes=""):
    """
    Constructs the Discord text block based on algorithm tiering.
    """
    direction_str = "BULLISH" if is_bull else "BEARISH"
    scalp_text = "SCALP " if is_scalp else ""
    scalp_emoji = " 🔪" if is_scalp else ""

    tier_config = {
        1: {"emoji": "🔥" if is_bull else "🩸", "strength": "EXTREME"},
        2: {"emoji": "🟢" if is_bull else "🔴", "strength": "STRONG"},
        3: {"emoji": "↗️" if is_bull else "↘️", "strength": "STANDARD"},
        4: {"emoji": "🛡️" if is_bull else "🧱", "strength": "STRUCTURE"},
        5: {"emoji": "⚠️", "strength": "WEAK"},
        6: {"emoji": "☠️", "strength": "VERY WEAK"}
    }

    cfg = tier_config.get(tier, {"emoji": "❓", "strength": "UNKNOWN"})

    clean_category = f"{cfg['strength']} {direction_str} {scalp_text}SETUP"
    stat_line = ""

    header_emojis = f"{cfg['emoji']}{scalp_emoji}"
    message = f"{header_emojis} **{clean_category}** {header_emojis}:\n"

    if triggers:
        if isinstance(triggers, list):
            message += f"Main Trigger: {', '.join(triggers)}\n"
        else:
            message += f"Main Trigger: {triggers}\n"

    if notes or stat_line:
        message += f"Extra Notes: {notes}{stat_line}\n"

    return message


def create_alert(vwap_rel, macro_flags, micro_flags, line_flags, oscillator, history):
    """
    Core decision engine: Evaluates confluence matrices to generate or invalidate trade alerts.
    """
    global prev_messageID
    vwap_rel = vwap_rel.lower()

    try:
        uptrend_ribbon = history[-1]['ema_short'] < history[-1]['ema_mid']
    except TypeError:
        for i in range(len(history)):
            idx = -1 * i
            try:
                uptrend_ribbon = history[idx]['ema_short'] < history[idx]['ema_mid']
                break
            except TypeError:
                continue
        uptrend_ribbon = True

    is_macro_support = macro_flags.get('support', False)
    is_micro_support = micro_flags.get('support', False)
    is_macro_resistance = macro_flags.get('resistance', False)
    is_micro_resistance = micro_flags.get('resistance', False)

    ema_short_tap_below = line_flags.get('EMA_SHORT_FROM_BELOW', False)
    ema_short_tap_above = line_flags.get('EMA_SHORT_FROM_ABOVE', False)
    ema_mid_tap_below = line_flags.get('EMA_MID_FROM_BELOW', False)
    ema_mid_tap_above = line_flags.get('EMA_MID_FROM_ABOVE', False)

    vwap_center_tap_above = line_flags.get('VWAP_CENTER_FROM_ABOVE', False)
    vwap_lower_tap_above = line_flags.get('VWAP_LOWER_FROM_ABOVE', False)
    vwap_upper_tap_above = line_flags.get('VWAP_UPPER_FROM_ABOVE', False)

    vwap_center_tap_below = line_flags.get('VWAP_CENTER_FROM_BELOW', False)
    vwap_lower_tap_below = line_flags.get('VWAP_LOWER_FROM_BELOW', False)
    vwap_upper_tap_below = line_flags.get('VWAP_UPPER_FROM_BELOW', False)

    bull_signals = {
        "Mid EMA": ema_mid_tap_above,
        "VWAP Center": vwap_center_tap_above,
        "VWAP Lower": vwap_lower_tap_above,
        "VWAP Upper": vwap_upper_tap_above
    }

    bear_signals = {
        "Mid EMA": ema_mid_tap_below,
        "VWAP Center": vwap_center_tap_below,
        "VWAP Lower": vwap_lower_tap_below,
        "VWAP Upper": vwap_upper_tap_below
    }

    active_bulls = [name for name, is_active in bull_signals.items() if is_active]
    active_bears = [name for name, is_active in bear_signals.items() if is_active]

    is_support = is_macro_support or is_micro_support
    is_resistance = is_macro_resistance or is_micro_resistance

    tier = 0
    is_bull = False
    is_scalp = False
    triggers = []
    notes = ""
    message_id = 0

    if len(active_bulls) >= 2 and is_macro_support:
        tier, is_bull, is_scalp, triggers, message_id = 1, True, False, active_bulls, 1
        notes = "Macro Support Bottom + Multiple Indicators"
    elif len(active_bulls) >= 2 and is_micro_support:
        tier, is_bull, is_scalp, triggers, message_id = 1, True, True, active_bulls, -2
        notes = "Micro Support Bottom + Multiple Indicators"
    elif is_support and len(active_bulls) >= 1:
        tier, is_bull, is_scalp, triggers, message_id = 2, True, False, active_bulls, 3
        notes = "Support Bottom + Single Indicator"
    elif len(active_bulls) >= 2:
        tier, is_bull, is_scalp, triggers, message_id = 3, True, False, active_bulls, 5
        notes = "Momentum Confluence (No S/R interaction)"
    elif is_macro_support:
        tier, is_bull, is_scalp, triggers, message_id = 4, True, False, [], 7
        notes = "Potential Local Bottom (Naked S/R Tap)"
    elif is_micro_support:
        tier, is_bull, is_scalp, triggers, message_id = 4, True, True, [], 7
        notes = "Potential Local Bottom (Naked S/R Tap)"
    elif vwap_rel == 'above' and ema_mid_tap_above:
        tier, is_bull, is_scalp, triggers, message_id = 5, True, True, ["Mid EMA"], 10
        notes = "Mid EMA Retest Above VWAP"
    elif len(active_bulls) >= 1:
        tier, is_bull, is_scalp, triggers, message_id = 6, True, False, active_bulls, 11
        notes = "Weak Momentum Tap"

    elif len(active_bears) >= 2 and is_macro_resistance:
        tier, is_bull, is_scalp, triggers, message_id = 1, False, False, active_bears, -20
        notes = "Macro Resistance Top + Multiple Indicators"
    elif len(active_bears) >= 2 and is_micro_resistance:
        tier, is_bull, is_scalp, triggers, message_id = 1, False, True, active_bears, 2
        notes = "Micro Resistance Top + Multiple Indicators"
    elif is_resistance and len(active_bears) >= 1:
        tier, is_bull, is_scalp, triggers, message_id = 2, False, False, active_bears, 4
        notes = "Resistance Top + Single Indicator"
    elif len(active_bears) >= 2:
        tier, is_bull, is_scalp, triggers, message_id = 3, False, False, active_bears, 6
        notes = "Momentum Confluence (No S/R interaction)"
    elif is_macro_resistance:
        tier, is_bull, is_scalp, triggers, message_id = 4, False, False, [], 8
        notes = "Potential Local Top (Naked S/R Tap)"
    elif is_micro_resistance:
        tier, is_bull, is_scalp, triggers, message_id = 4, False, True, [], 8
        notes = "Potential Local Top (Naked S/R Tap)"
    elif vwap_rel == 'below' and ema_mid_tap_below:
        tier, is_bull, is_scalp, triggers, message_id = 5, False, True, ["Mid EMA"], 9
        notes = "Mid EMA Retest Below VWAP"
    elif len(active_bears) >= 1:
        tier, is_bull, is_scalp, triggers, message_id = 6, False, False, active_bears, 12
        notes = "Weak Momentum Tap"

    if tier > 0:
        if is_bull:
            if vwap_rel == 'above':
                tier -= 1
                notes += " | Upgraded: With VWAP (+)"
            elif vwap_rel == 'below':
                tier += 2
                notes += " | Downgraded: Fighting VWAP (-)"

        elif not is_bull:
            if vwap_rel == 'below':
                tier -= 1
                notes += " | Upgraded: With VWAP (+)"
            elif vwap_rel == 'above':
                tier += 2
                notes += " | Downgraded: Fighting VWAP (-)"

        tier = max(1, min(tier, 6))

    if tier == 0 or message_id == prev_messageID:
        return "None", 0

    if oscillator > config.OSCILLATOR_ABSOLUTE_CAP and not is_bull:
        return "None", 0
    if oscillator > config.OSCILLATOR_WARNING_CAP and not is_bull:
        if tier >= 5: return "None", 0
        notes += "\n\t\t\tStrong Oscillator - Expect an invalidation or a very quick move"

    if oscillator < -config.OSCILLATOR_ABSOLUTE_CAP and is_bull:
        return "None", 0
    if oscillator < -config.OSCILLATOR_WARNING_CAP and is_bull:
        if tier >= 5: return "None", 0
        notes += "\n\t\t\tStrong Oscillator - Expect an invalidation or a very quick move"

    chop_density = get_chop_density(history, config.CHOP_DENSITY_LOOKBACK)

    if tier <= 4 and not is_scalp and chop_density > config.MAX_CHOP_DENSITY:
        # TODO maybe remove the is_scalp line since it dumps wr 0.9
        # TODO Ribbon Spread might be a good idea
        # return "None", 0
        pass

    echops = ensemble_chop_oscillator(history)
    density_ensemble_chop = density_ensemble_chop_oscillator(history)

    if echops > config.MAX_ECHOPS_SCORE and not is_scalp:
        notes += "\n\t\t\tEchops no Like + no scalp"
        # return "None", 0
    else:
        notes += f"\n\t\t\tEchops: {echops}"

    if density_ensemble_chop > config.MAX_DENSITY_ECHOPS_SCORE and not is_scalp:
        notes += "\n\t\t\tDensity E-Chop no Like"
        # return "None", 0
    else:
        notes += f"\n\t\t\tDensity E-Chop: {density_ensemble_chop}"

    if tier > 1 and is_bull and not is_scalp and vwap_rel == 'above':
        return "None", 0
        tier -= 1

    if tier > 1 and not is_bull and not is_scalp and vwap_rel == 'below':
        return "None", 0
        tier -= 1

    final_message = format_discord_alert(tier, is_bull, is_scalp, triggers, notes)
    return final_message, message_id

def filter_new_session(history, vertical_gap_threshold=15):
    """
    Slices the candle history to only include the current session
    by detecting overnight vertical price gaps.
    """
    if len(history) <= 1:
        return history

    session_start_idx = 0

    for i in range(len(history) - 1, 0, -1):
        prev_close = history[i - 1]['close']
        curr_open = history[i]['open']

        if abs(curr_open - prev_close) > vertical_gap_threshold:
            session_start_idx = i
            break

    return history[session_start_idx:]