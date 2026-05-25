import asyncio
import os
import config
from playwright.async_api import async_playwright
import cv2
import numpy as np
import io
from contextlib import redirect_stdout
import requests
from SR_algo_v1 import calculate_algo_sr

current_dir = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.join(current_dir, "tradingview_session")


async def run_scanner(CHART_URL, filename, HEADLESS=True):
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=HEADLESS,  # False if dumb valentines day ad prevents this from working
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1920, "height": 1080}
        )

        page = context.pages[0]
        await page.goto(CHART_URL)

        try:
            await page.wait_for_selector('canvas', timeout=10000)
        except:
            print("--- LOGIN REQUIRED ---")
            print("Please log in to TradingView in the browser window now.")
            await page.wait_for_selector('canvas', timeout=120000)
            print("Login successful. Session saved.")

        await page.evaluate("""
                            const hide = (s) => {
                                const el = document.querySelector(s);
                                if (el) el.style.display = 'none';
                            };
                            hide('[class*="widgetbar-"]');
                            hide('[class*="order-panel-"]');
                            hide('[class*="layout__area--top"]');
                            """)

        await asyncio.sleep(1.6)  # Let     indicators load
        viewport = page.viewport_size
        await page.mouse.click(viewport['width'] / 2, viewport['height'] / 2)
        await page.keyboard.press("Alt+R")
        await asyncio.sleep(0.5)
        for _ in range(7):
            await page.mouse.wheel(0, -100)
            await asyncio.sleep(0.05)

        await page.screenshot(path=filename)
        await context.close()


def send_to_discord(content, webhook_file, PING_DISCORD=True):
    if not PING_DISCORD: return


    try:
        with open(webhook_file, "r") as f:
            webhook_url = f.read().strip()
    except FileNotFoundError:
        print("config.txt not found.")
        return

    ping_str = f"<@{config.DISCORD_ID}> 🚨 **Day Trade Setup Detected!**🚨"

    if len(content) > 1800:
        chunks = [content[i:i + 1800] for i in range(0, len(content), 1800)]
        for i, chunk in enumerate(chunks):
            payload = {"content": f"{ping_str}\n```\n{chunk}\n```" if i == 0 else f"```\n{chunk}\n```"}
            requests.post(webhook_url, json=payload)
    else:
        payload = {"content": f"{ping_str}\n```\n{content}\n```"}
        requests.post(webhook_url, json=payload)


def send_to_discord_new(start_msg, content, webhook_file, PING_DISCORD=True):
    # Gets around the antivirus, thanks bitdefender
    if not PING_DISCORD: return

    try:
        with open(webhook_file, "r") as f:
            webhook_url = f.read().strip()
    except FileNotFoundError:
        print("config.txt not found!")
        return

    ping_str = f"<@{config.DISCORD_ID}> {start_msg}"

    if len(content) > 1800:
        chunks = [content[i:i + 1800] for i in range(0, len(content), 1800)]
        for i, chunk in enumerate(chunks):
            payload = {"content": f"{ping_str}\n```\n{chunk}\n```" if i == 0 else f"```\n{chunk}\n```"}
            requests.post(webhook_url, json=payload)
    else:
        payload = {"content": f"{ping_str}\n```\n{content}\n```"}
        requests.post(webhook_url, json=payload)


def crop_and_save_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image at '{image_path}'")
        return None

    h, w, _ = img.shape

    roi_top = int(h * config.CROP_TOP)
    roi_bot = int(h * config.CROP_BOT)
    roi_right = int(w * config.CROP_RIGHT)

    cropped_roi = img[roi_top:roi_bot, 0:roi_right]

    directory, original_filename = os.path.split(image_path)
    new_filename = f"cropped_{original_filename}"
    new_filepath = os.path.join(directory, new_filename)

    cv2.imwrite(new_filepath, cropped_roi)
    return new_filepath


def scan_chart_candles(image_path, emas=None, lines=None, ENABLE_ALGO=False, ALGO_DEBUG=False, SHOW_IMAGE=False):
    roi = cv2.imread(image_path)
    if roi is None: return []

    roi_h, roi_w, _ = roi.shape
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    def create_mask(color_name):
        ranges = config.TV_PALETTE.get(color_name.lower(), [])
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in ranges:
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, np.array(lower), np.array(upper)))
        return mask

    m_bull = create_mask('green')
    m_bear = create_mask('red')

    emas = emas or {}
    lines = lines or {}

    k_ema = np.ones((2, 2), np.uint8)
    ema_masks = {name: cv2.dilate(create_mask(color), k_ema) for name, color in emas.items()}
    line_masks = {name: create_mask(color) for name, color in lines.items()}

    def get_line_ys(mask, target_x):
        dilated = cv2.dilate(mask, np.ones((2, 2), np.uint8))
        hough_lines = cv2.HoughLinesP(
            dilated, 1, np.pi / 180,
            threshold=config.HOUGH_THRESHOLD,
            minLineLength=config.HOUGH_MIN_LINE_LENGTH,
            maxLineGap=config.HOUGH_MAX_LINE_GAP
        )
        found = []
        if hough_lines is not None:
            for line in hough_lines:
                x1, y1, x2, y2 = line[0]
                if min(x1, x2) <= target_x <= max(x1, x2):
                    if x1 == x2: found.append(y1); continue
                    y_at_x = y1 + (y2 - y1) * (target_x - x1) / (x2 - x1)
                    found.append(int(y_at_x))
        return sorted(list(set(found)))

    def find_indicator_at_x(mask, x_c, w_c):
        strip = mask[:, max(0, x_c - 4):min(roi_w, x_c + w_c + 4)]
        coords = np.where(strip > 0)[0]
        return int(np.median(coords)) if len(coords) > 0 else None

    m_all = cv2.bitwise_or(m_bull, m_bear)
    v_kernel = np.ones((3, 1), np.uint8)
    m_repaired = cv2.morphologyEx(m_all, cv2.MORPH_CLOSE, v_kernel)

    contours, _ = cv2.findContours(m_repaired, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candle_history = []

    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)

        # noise filters
        if cw < config.MIN_CANDLE_WIDTH or ch < config.MIN_CANDLE_HEIGHT or (y + ch) > (
                roi_h * 1) or cw > config.MAX_CANDLE_WIDTH:
            continue

        roi_bull = m_bull[y:y + ch, x:x + cw]
        roi_bear = m_bear[y:y + ch, x:x + cw]
        is_bullish = cv2.countNonZero(roi_bull) > cv2.countNonZero(roi_bear)

        row_widths = [cv2.countNonZero(m_repaired[y + i, x:x + cw]) for i in range(ch)]
        max_w = max(row_widths) if row_widths else 0

        # Abstracted body-to-wick ratio
        thick_rows = [i for i, v in enumerate(row_widths) if v >= max_w * config.CANDLE_BODY_RATIO]

        if thick_rows:
            bt, bb = y + min(thick_rows), y + max(thick_rows)
            o_px, c_px = (bb, bt) if is_bullish else (bt, bb)
        else:
            o_px = c_px = y + ch // 2

        x_mid = x + cw // 2

        candle_data = {
            'x_mid': x_mid,
            'color': "Bullish" if is_bullish else "Bearish",
            'high': y, 'low': y + ch,
            'open': int(o_px), 'close': int(c_px),
            'algo_sr': []
        }

        for ema_name, ema_mask in ema_masks.items():
            candle_data[ema_name] = find_indicator_at_x(ema_mask, x, cw)

        for line_name, line_mask in line_masks.items():
            candle_data[f"{line_name}_ys"] = get_line_ys(line_mask, x_mid)

        candle_history.append(candle_data)

    candle_history = sorted(candle_history, key=lambda k: k['x_mid'])

    BGR_MAP = {
        'green': (0, 255, 0), 'lime': (0, 255, 150), 'red': (0, 0, 255),
        'blue': (255, 0, 0), 'light_blue': (255, 255, 0), 'cyan': (255, 255, 0),
        'orange': (0, 165, 255), 'purple': (255, 0, 255), 'yellow': (0, 255, 255),
        'magenta': (255, 0, 255)
    }

    if SHOW_IMAGE or ALGO_DEBUG:
        debug_img = roi.copy()
        for c in candle_history:
            xm = c['x_mid']
            cv2.line(debug_img, (xm, c['high']), (xm, c['low']), (255, 255, 255), 1)
            color_bgr = (0, 255, 0) if c['color'] == "Bullish" else (0, 0, 255)
            top, bot = sorted([c['open'], c['close']])
            if top == bot: bot += 1
            cv2.rectangle(debug_img, (xm - 2, top), (xm + 2, bot), color_bgr, 1)

            for ema_name, color_name in emas.items():
                if c.get(ema_name):
                    dot_color = BGR_MAP.get(color_name.lower(), (255, 255, 255))
                    cv2.circle(debug_img, (xm, c[ema_name]), 2, dot_color, -1)

            for line_name in lines.keys():
                for y_val in c.get(f"{line_name}_ys", []):
                    cv2.circle(debug_img, (xm, y_val), 2, (200, 200, 200), -1)

    if SHOW_IMAGE:
        cv2.imshow("Scanner Debug", debug_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    if ENABLE_ALGO:
        algo_sr = calculate_algo_sr(candle_history)
        for candle in candle_history:
            candle['algo_sr'] = algo_sr

    return candle_history