import io
import config
from contextlib import redirect_stdout
from collections import Counter
from candle_patterns_and_momentum import ensemble_chop_oscillator, get_algorithmic_momentum, get_specific_candle_type, \
    is_ribbon_fanning

# TODO add back invalidation
# TODO fix algo so it actually works on this new system again

class SetupEngine:
    VALID_SETUPS = {
        'breadth': "Breadth Gauge",
        'trending_inside_day': "⏸️ Trending Inside Day",
        'ema_short_pullback': "🎣 EMA Short Pullback",
        'ema_mid_pullback': "🎣 EMA Mid Pullback",
        'ema_long_pullback': "🎣 EMA Long Pullback",
        'line_pullback': "🔵 Line Pullback",
        'line_breakout': "🚀 Line Breakout",
        'algo_pullback_old': "⚙️ Algo Pullback (Lines)",
        'algo_pullback_new': "🟩 Algo Pullback (Zones)",
        'non_algo_confluence': "⚪ Non-Algo Confluence",
        'algo_confluence_old': "🌟 Algo Confluence (Lines)",
        'algo_confluence_new': "✨ Algo Confluence (Zones)"
    }

    def __init__(self, active_setups, lookback=config.DEFAULT_LOOKBACK):
        self.total = 0
        self.div_len = 66
        self.active_setups = active_setups
        self.lookback = lookback

        for s in self.active_setups:
            if s not in self.VALID_SETUPS:
                raise ValueError(f"Invalid setup '{s}'. Valid options: {list(self.VALID_SETUPS.keys())}")

        self.setups = {
            self.VALID_SETUPS[s]: {"bull": set(), "bear": set()}
            for s in self.active_setups if s != 'breadth'
        }
        self.breadth = {
            "Green Close": set(),  "Above Short EMA": set(),
            "Above Mid EMA": set(), "Above Long EMA": set(), "Bull Ribbon": set(),
            "New Highs": set(), "New Lows": set()
        }

    def process_ticker(self, ticker, history):
        if not history or len(history) < max(2, self.lookback):
            return

        self.total += 1
        c, p = history[-1], history[-2]
        recent_history = history[-self.lookback:]

        cond = {
            'inside_day': (c['high'] >= p['high']) and (c['low'] <= p['low']),
            'green_close': c['close'] < p['close'],
            'above_short': c['close'] < c['ema_short'] if c.get('ema_short') else False,
            'above_mid': c['close'] < c['ema_mid'] if c.get('ema_mid') else False,
            'above_long': c['close'] < c['ema_long'] if c.get('ema_long') else False,
            'below_short': c['close'] > c['ema_short'] if c.get('ema_short') else False,
            'below_mid': c['close'] > c['ema_mid'] if c.get('ema_mid') else False,
            'ribbon_bull': c['ema_short'] < c['ema_mid'] if (c.get('ema_short') and c.get('ema_mid')) else False,
            'ribbon_bear': c['ema_short'] > c['ema_mid'] if (c.get('ema_short') and c.get('ema_mid')) else False,
        }

        window_size = config.BREADTH_HIGH_LOW_WINDOW
        past_window = history[-(window_size + 1):-1]

        if past_window:
            cond['new_high'] = c['high'] < min(x['high'] for x in past_window)
            cond['new_low'] = c['low'] > max(x['low'] for x in past_window)
        else:
            cond['new_high'], cond['new_low'] = False, False

        if 'breadth' in self.active_setups:
            self._update_breadth(ticker, cond)
        if 'trending_inside_day' in self.active_setups:
            self._id_trending_inside_day(ticker, cond)
        if any(x in self.active_setups for x in ['ema_short_pullback', 'ema_mid_pullback', 'ema_long_pullback']):
            self._id_ema_pullbacks(ticker, history, cond)
        if 'line_pullback' in self.active_setups:
            self._id_line_pullback(ticker, history, cond)
        if 'line_breakout' in self.active_setups:
            self._id_line_breakout(ticker, history, cond)
        if 'algo_pullback_old' in self.active_setups:
            self._id_algo_pullback_old(ticker, history, cond)
        if 'algo_pullback_new' in self.active_setups:
            self._id_algo_pullback_new(ticker, history, cond)
        if 'non_algo_confluence' in self.active_setups:
            self._id_non_algo_confluence(ticker, history, cond)
        if 'algo_confluence_old' in self.active_setups:
            self._id_algo_confluence_old(ticker, history, cond)
        if 'algo_confluence_new' in self.active_setups:
            self._id_algo_confluence_new(ticker, history, cond)

    def _update_breadth(self, ticker, cond):
        if cond['green_close']: self.breadth["Green Close"].add(ticker)
        if cond['above_short']: self.breadth["Above Short EMA"].add(ticker)
        if cond['above_mid']: self.breadth["Above Mid EMA"].add(ticker)
        if cond['above_long']: self.breadth["Above Long EMA"].add(ticker)
        if cond['ribbon_bull']: self.breadth["Bull Ribbon"].add(ticker)
        if cond.get('new_high'): self.breadth["New Highs"].add(ticker)
        if cond.get('new_low'): self.breadth["New Lows"].add(ticker)

    def _id_trending_inside_day(self, ticker, cond):
        if cond['inside_day']:
            if (cond['above_short'] and cond['above_mid']):
                self.setups[self.VALID_SETUPS['trending_inside_day']]["bull"].add(ticker)
            elif cond['below_short'] and cond['below_mid']:
                self.setups[self.VALID_SETUPS['trending_inside_day']]["bear"].add(ticker)

    def _id_ema_pullbacks(self, ticker, history, cond):
        """Identifies dynamic moving average pullbacks based on configured thresholds."""
        c = history[-1]
        thresh = config.PULLBACK_THRESH
        pierce = config.PULLBACK_PIERCE

        bulls = {'ema_short': False, 'ema_mid': False, 'ema_long': False}
        bears = {'ema_short': False, 'ema_mid': False, 'ema_long': False}

        for candle in history[-self.lookback:]:
            for k in bulls.keys():
                ema = candle.get(k)
                if not ema: continue

                dist_low = abs(candle['low'] - ema)
                if dist_low <= thresh and candle['close'] <= (ema + pierce):
                    bulls[k] = True

                dist_high = abs(candle['high'] - ema)
                if dist_high <= thresh and candle['close'] >= (ema - pierce):
                    bears[k] = True

        for k in bulls.keys():
            s_name = f"{k}_pullback"
            if s_name not in self.active_setups: continue

            if bulls[k]:
                self.setups[self.VALID_SETUPS[s_name]]["bull"].add(ticker)
            if bears[k]:
                self.setups[self.VALID_SETUPS[s_name]]["bear"].add(ticker)

    def _id_line_pullback(self, ticker, history, cond):
        thresh = config.PULLBACK_THRESH
        pierce = config.PULLBACK_PIERCE

        bull_tap = False
        bear_tap = False

        for candle in history[-self.lookback:]:
            lines = candle.get('orange_ys', []) + candle.get('blue_ys', [])

            for lvl in lines:
                dist_low = abs(candle['low'] - lvl)
                dist_high = abs(candle['high'] - lvl)
                if dist_low <= thresh and candle['close'] <= (lvl + pierce):
                    bull_tap = True

                if dist_high <= thresh and candle['close'] >= (lvl - pierce):
                    bear_tap = True

        if bull_tap:
            self.setups[self.VALID_SETUPS['line_pullback']]['bull'].add(ticker)

        if bear_tap:
            self.setups[self.VALID_SETUPS['line_pullback']]['bear'].add(ticker)

    def _id_line_breakout(self, ticker, history, cond):
        buffer = config.BREAKOUT_BUFFER
        bull_bo = False
        bear_bo = False

        start_idx = max(1, len(history) - self.lookback)  # self is why I dont like using classes

        for i in range(len(history) - 1, start_idx - 1, -1):
            curr = history[i]
            prev = history[i - 1]

            lines = curr.get('orange_ys', []) + curr.get('blue_ys', [])
            if not lines: continue

            c_curr, o_curr = curr['close'], curr['open']
            c_prev = prev['close']

            is_green = c_curr < o_curr
            is_red = c_curr > o_curr

            for lvl in lines:
                if lvl is None: continue
                if is_green:
                    breakthrough = (o_curr > lvl) and (c_curr <= lvl - buffer)
                    gap = (c_prev > lvl) and (o_curr <= lvl - buffer) and (c_curr <= lvl - buffer)

                    if breakthrough or gap:
                        is_valid = True
                        for j in range(i + 1, len(history)):
                            if history[j]['open'] > (lvl - buffer) or history[j]['close'] > (lvl - buffer):
                                is_valid = False
                                break
                        if is_valid:
                            bull_bo = True
                if is_red:
                    breakthrough = (o_curr < lvl) and (c_curr >= lvl + buffer)
                    gap = (c_prev < lvl) and (o_curr >= lvl + buffer) and (c_curr >= lvl + buffer)

                    if breakthrough or gap:
                        is_valid = True
                        for j in range(i + 1, len(history)):
                            if history[j]['open'] < (lvl + buffer) or history[j]['close'] < (lvl + buffer):
                                is_valid = False
                                break
                        if is_valid:
                            bear_bo = True
            if bull_bo or bear_bo:
                break
        if bull_bo:
            self.setups[self.VALID_SETUPS['line_breakout']]['bull'].add(ticker)
        if bear_bo:
            self.setups[self.VALID_SETUPS['line_breakout']]['bear'].add(ticker)

    def _id_algo_pullback_old(self, ticker, history, cond):
        thresh = config.PULLBACK_THRESH
        pierce = config.PULLBACK_PIERCE
        bull_tap = False
        bear_tap = False

        candle = history[-1]
        for lvl in candle.get('algo_sr', []):
            if lvl is None: continue
            dist_low = abs(candle['low'] - lvl)
            dist_high = abs(candle['high'] - lvl)

            if dist_low <= thresh and candle['close'] <= (lvl + pierce):
                bull_tap = True

            if dist_high <= thresh and candle['close'] >= (lvl - pierce):
                bear_tap = True

        if bull_tap:
            self.setups[self.VALID_SETUPS['algo_pullback_old']]['bull'].add(ticker)

        if bear_tap:
            self.setups[self.VALID_SETUPS['algo_pullback_old']]['bear'].add(ticker)

    def _id_algo_pullback_new(self, ticker, history, cond):
        # TODO write this eventually it might be a pain because its not built into the dictionary cause its day scanner's function
        pass

    def _id_non_algo_confluence(self, ticker, history, cond):
        thresh = config.PULLBACK_THRESH
        pierce = config.PULLBACK_PIERCE

        bull_conf = False
        bear_conf = False

        for candle in history[-self.lookback:]:
            emas = [e for e in [candle.get('ema_short'), candle.get('ema_mid'), candle.get('ema_long')] if e]
            lines = candle.get('orange_ys', []) + candle.get('blue_ys', [])

            if not emas or not lines: continue

            c_bull_ema, c_bull_line = False, False
            c_bear_ema, c_bear_line = False, False

            # Check EMAs
            for ema in emas:
                if abs(candle['low'] - ema) <= thresh and candle['close'] <= (ema + pierce):
                    c_bull_ema = True
                if abs(candle['high'] - ema) <= thresh and candle['close'] >= (ema - pierce):
                    c_bear_ema = True

            # Check Lines
            for lvl in lines:
                if lvl is None: continue
                if abs(candle['low'] - lvl) <= thresh and candle['close'] <= (lvl + pierce):
                    c_bull_line = True
                if abs(candle['high'] - lvl) <= thresh and candle['close'] >= (lvl - pierce):
                    c_bear_line = True

            if c_bull_ema and c_bull_line:
                bull_conf = True
            if c_bear_ema and c_bear_line:
                bear_conf = True

        if bull_conf:
            self.setups[self.VALID_SETUPS['non_algo_confluence']]['bull'].add(ticker)
        if bear_conf:
            self.setups[self.VALID_SETUPS['non_algo_confluence']]['bear'].add(ticker)

    def _id_algo_confluence_old(self, ticker, history, cond):
        thresh = config.PULLBACK_THRESH
        pierce = config.PULLBACK_PIERCE
        bull_conf = False
        bear_conf = False

        candle = history[-1]
        emas = [e for e in [candle.get('ema_short'), candle.get('ema_mid'), candle.get('ema_long')] if e]
        algo_lines = candle.get('algo_sr', [])

        c_bull_ema, c_bear_ema = False, False
        c_bull_algo, c_bear_algo = False, False

        # Check EMAs
        for ema in emas:
            if abs(candle['low'] - ema) <= thresh and candle['close'] <= (ema + pierce):
                c_bull_ema = True
            if abs(candle['high'] - ema) <= thresh and candle['close'] >= (ema - pierce):
                c_bear_ema = True

        # Check Algo Lines
        for lvl in algo_lines:
            if lvl is None: continue
            if abs(candle['low'] - lvl) <= thresh and candle['close'] <= (lvl + pierce):
                c_bull_algo = True
            if abs(candle['high'] - lvl) <= thresh and candle['close'] >= (lvl - pierce):
                c_bear_algo = True

        if c_bull_ema and c_bull_algo:
            bull_conf = True
        if c_bear_ema and c_bear_algo:
            bear_conf = True

        if bull_conf:
            self.setups[self.VALID_SETUPS['algo_confluence_old']]['bull'].add(ticker)
        if bear_conf:
            self.setups[self.VALID_SETUPS['algo_confluence_old']]['bear'].add(ticker)

    def _id_algo_confluence_new(self, ticker, history, cond):
        # TODO Write this logic
        pass

    def _create_divider(self, border):
        border = border.lower()
        if border == 'top':
            print("\n" + "╔" + "═" * self.div_len + "╗")
        elif border == 'bottom':
            print("╚" + "═" * self.div_len + "╝")
        elif border == 'middle':
            print("╠" + "═" * self.div_len + "╣")
        elif border == 'mini':
            print("╠" + "-" * self.div_len + "╣")

    def _p_row(self, label, data, icon="•"):
        if not data: return
        t_str = ", ".join(data)
        print(f"║ {icon} {label:<22} : {t_str}")

    def _print_breadth(self, label, count):
        safe_total = max(1, self.total)
        pct = (count / safe_total) * 100
        bar_len = 19
        filled = int((pct / 100) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)

        if pct > config.BREADTH_LEVELS['extreme_bull']:
            emoji = "🔥"
        elif config.BREADTH_LEVELS['bull'] < pct <= config.BREADTH_LEVELS['extreme_bull']:
            emoji = '✅'
        elif config.BREADTH_LEVELS['neutral'] < pct <= config.BREADTH_LEVELS['bull']:
            emoji = '⚖️'
        elif config.BREADTH_LEVELS['bear'] < pct <= config.BREADTH_LEVELS['neutral']:
            emoji = '⚠️'
        else:
            emoji = '🆘'

        print(f"║ {emoji} {label:<15} : [{bar}] {pct:>4.1f}% ({count}/{self.total})")

    def generate_report(self):
        """Formats and prints the parsed market scan data to the console."""
        # The Great Purge
        if 'non_algo_confluence' in self.active_setups:
            na_conf = self.VALID_SETUPS['non_algo_confluence']
            na_subs = [self.VALID_SETUPS[s] for s in
                       ['ema_short_pullback', 'ema_mid_pullback', 'ema_long_pullback', 'line_pullback'] if
                       s in self.active_setups]
            for side in ['bull', 'bear']:
                for ticker in list(self.setups[na_conf][side]):
                    for sub in na_subs:
                        if ticker in self.setups[sub][side]:
                            self.setups[sub][side].remove(ticker)

        if 'algo_confluence_old' in self.active_setups:
            aco_conf = self.VALID_SETUPS['algo_confluence_old']
            aco_subs = [self.VALID_SETUPS[s] for s in
                        ['ema_short_pullback', 'ema_mid_pullback', 'ema_long_pullback', 'algo_pullback_old'] if
                        s in self.active_setups]
            for side in ['bull', 'bear']:
                for ticker in list(self.setups[aco_conf][side]):
                    for sub in aco_subs:
                        if ticker in self.setups[sub][side]:
                            self.setups[sub][side].remove(ticker)

        all_bull, all_bear = [], []
        for s in self.setups.values():
            all_bull.extend(list(s["bull"]))
            all_bear.extend(list(s["bear"]))

        b_counts = Counter(all_bull)
        br_counts = Counter(all_bear)

        f = io.StringIO()
        with redirect_stdout(f):
            self._create_divider('top')
            print(f"║{'MARKET SCAN SUMMARY (Lookback: ' + str(self.lookback) + ')':^{self.div_len}}║")

            if 'breadth' in self.active_setups:
                self._create_divider('middle')
                print(f"║ BREADTH GAUGE")
                self._create_divider('mini')
                for l, t in self.breadth.items():
                    self._print_breadth(l, len(t))

            for side, label, counts in [('bull', '🟢 BULLISH SETUPS', b_counts),
                                        ('bear', '🔴 BEARISH SETUPS', br_counts)]:
                if any(s[side] for s in self.setups.values()):
                    self._create_divider('middle')
                    print(f"║ {label}")
                    self._create_divider('mini')
                    for name, data in self.setups.items():
                        fmt = [f"{t}*" if counts[t] > 1 else t for t in sorted(list(data[side]))]
                        if fmt:
                            icon, text = name.split(" ", 1)
                            self._p_row(text, fmt, icon)

            self._create_divider('bottom')

        return f.getvalue()
