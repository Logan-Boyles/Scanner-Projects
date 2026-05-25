import math
import config


def get_specific_candle_type(candle):
    """
    Evaluates pixel matrices to classify candle morphology based on proprietary body-to-wick percentage thresholds.
    """
    total_range = abs(candle['high'] - candle['low'])

    if candle['close'] > candle['open']:
        color = "red"
    elif candle['close'] < candle['open']:
        color = "green"
    else:
        color = "flat"

    if total_range == 0:
        return {
            "color": color,
            "type": "doji",
            "body_pct": 0,
            "upper_wick_pct": 0,
            "lower_wick_pct": 0
        }

    body = abs(candle['close'] - candle['open'])
    top_of_body = min(candle['open'], candle['close'])
    bottom_of_body = max(candle['open'], candle['close'])
    wick_high = top_of_body - candle['high']
    wick_low = candle['low'] - bottom_of_body

    body_pct = (body / total_range) * 100
    upper_wick_pct = (wick_high / total_range) * 100
    lower_wick_pct = (wick_low / total_range) * 100

    candle_type = "standard"

    if body_pct >= config.CANDLE_MOMENTUM_PCT:
        candle_type = "strength"
    elif lower_wick_pct >= config.CANDLE_HAMMER_WICK_PCT and upper_wick_pct <= config.CANDLE_HAMMER_BODY_PCT:
        candle_type = "hammer"
    elif upper_wick_pct >= config.CANDLE_HAMMER_WICK_PCT and lower_wick_pct <= config.CANDLE_HAMMER_BODY_PCT:
        candle_type = "shooting star"
    elif body_pct <= config.CANDLE_DOJI_PCT:
        candle_type = "doji"

    return candle_type, color


def get_candle_patterns(history):
    pass


def get_algorithmic_momentum(history, lookback=config.MOMENTUM_LOOKBACK):
    """
    Generates a custom -1 to 1 momentum gauge using a hyperbolic tangent (tanh) function,
    weighted by recency, pixel size dispersion, and structural flags.
    """
    if len(history) < lookback:
        return 0.0

    window = history[-lookback:]

    bodies = [abs(c['close'] - c['open']) for c in window]
    avg_body = sum(bodies) / lookback

    if avg_body == 0:
        return 0.0

    raw_score = 0.0

    for i in range(lookback):
        current = window[i]
        body = bodies[i]

        direction = 1 if current['close'] < current['open'] else -1
        if current['close'] == current['open']:
            direction = 0

        size_factor = body / avg_body
        recency_weight = ((i + 1) / lookback) ** config.RECENCY_DECAY_FACTOR
        flag_factor = 1.0

        if i > 0:
            prev = window[i - 1]
            prev_direction = 1 if prev['close'] < prev['open'] else -1

            if direction != prev_direction and body < (bodies[i - 1] * config.MOMENTUM_SIZE_MODIFIER):
                flag_factor = config.MOMENTUM_FLAG_WEIGHT

        raw_score += direction * size_factor * recency_weight * flag_factor

    final_gauge = math.tanh(raw_score)

    return round(final_gauge, 3)


def get_true_range(current_candle, previous_candle):
    high_low = current_candle['high'] - current_candle['low']
    high_prev_close = abs(current_candle['high'] - previous_candle['close'])
    low_prev_close = abs(current_candle['low'] - previous_candle['close'])

    return max(high_low, high_prev_close, low_prev_close)


def calculate_atr(history, period=config.ATR_PERIOD):
    """Calculates Average True Range based on pixel volatility."""
    if len(history) < period + 1:
        return None

    true_ranges = []
    for i in range(-period, 0):
        tr = get_true_range(history[i], history[i - 1])
        true_ranges.append(tr)

    return sum(true_ranges) / period


def get_chop_density(history, lookback=config.DENSITY_LOOKBACK):
    """
    Calculates the density of candle bodies within their collective bounding box.
    1.0 = Pure Trend (No overlap). > 2.0 = Heavy Chop.
    """
    if len(history) < lookback:
        return 1.0

    recent = history[-lookback:]

    total_body_height = 0
    tops = []
    bottoms = []

    for c in recent:
        top = min(c['open'], c['close'])
        bot = max(c['open'], c['close'])

        total_body_height += (bot - top)
        tops.append(top)
        bottoms.append(bot)

    box_top = min(tops)
    box_bot = max(bottoms)
    box_height = box_bot - box_top

    if box_height == 0:
        return 99.0

    density = total_body_height / box_height
    return density


def get_consolidation_ratio(history, lookback=config.DENSITY_LOOKBACK, macro_lookback=config.MACRO_LOOKBACK):
    """
    Detects 'Dead Zones' by evaluating if a cluster of recent candles
    is trapped inside the normal space of a single macro-average candle.
    """
    if len(history) < macro_lookback:
        return 0.0

    baseline = history[-macro_lookback:]

    avg_candle_height = sum(abs(c['low'] - c['high']) for c in baseline) / macro_lookback
    avg_candle_height = max(1.0, avg_candle_height)

    recent = history[-lookback:]

    box_top = min(min(c['high'], c['low']) for c in recent)
    box_bot = max(max(c['high'], c['low']) for c in recent)

    cluster_box_height = max(1.0, box_bot - box_top)

    ratio = avg_candle_height / cluster_box_height
    return round(ratio, 3)


def is_ribbon_fanning(candle, min_pixel_spread=config.MIN_RIBBON_PIXEL_SPREAD):
    """
    Validates EMA ribbon velocity against minimum pixel spread parameters to filter sideways grinds.
    """
    ema_short = candle.get('ema_short')
    ema_mid = candle.get('ema_mid')

    if ema_short is None or ema_mid is None:
        return False

    spread = abs(ema_short - ema_mid)

    return spread >= min_pixel_spread


def get_atr_adjusted_consolidation(history, lookback=config.ATR_ADJUST_LOOKBACK, macro_lookback=config.MACRO_LOOKBACK):
    """
    Measures Net Movement vs Total Range, scaled dynamically by Volatility (Pixel ATR).
    """
    if len(history) < macro_lookback: return 0.0

    macro_atr = sum(abs(c['high'] - c['low']) for c in history[-macro_lookback:]) / macro_lookback
    micro_atr = sum(abs(c['high'] - c['low']) for c in history[-lookback:]) / lookback
    volatility_multiplier = min(config.MAX_VOLATILITY_MULTIPLIER, max(1.0, macro_atr) / max(1.0, micro_atr))
    window = history[-lookback:]
    start_price = window[0]['open']
    end_price = window[-1]['close']
    net_move = abs(end_price - start_price)

    box_top = min(min(c['high'], c['low']) for c in window)
    box_bot = max(max(c['high'], c['low']) for c in window)
    total_range = max(1.0, box_bot - box_top)

    base_consolidation = 1.0 - (net_move / total_range)

    final_score = min(1.0, base_consolidation * volatility_multiplier)
    return round(final_score, 3)


def ensemble_chop_oscillator(history):
    """Averages multi-timeframe ATR-adjusted consolidation logic into a single output."""
    w1, w2, w3 = config.CHOP_ENSEMBLE_WINDOWS

    o1 = get_atr_adjusted_consolidation(history, w1)
    o2 = get_atr_adjusted_consolidation(history, w2)
    o3 = get_atr_adjusted_consolidation(history, w3)

    avg = (o1 + o2 + o3) / 3
    return round(avg, 3)