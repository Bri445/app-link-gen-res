"""
link_resolver_gui.py
Tkinter GUI that uses Selenium to open a link, click Verify -> Continue, wait for countdowns,
follow redirects and extract the 'Get Link' URL.

Requirements:
    pip install selenium webdriver-manager

Works best with Chrome installed.
"""

import threading
import time
import traceback
from urllib.parse import urlparse

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options

# --------------------------
# Helper / Automation logic
# --------------------------

def safe_log(log_widget, text):
    log_widget.configure(state="normal")
    log_widget.insert(tk.END, f"{text}\n")
    log_widget.see(tk.END)
    log_widget.configure(state="disabled")

def wait_for_element(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))

def element_click_if_present(driver, by, value, timeout=5):
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        el.click()
        return True
    except Exception:
        return False

def click_button_by_text(driver, text, timeout=5):
    """Try to click a button or link whose visible text matches 'text' (case-insensitive)."""
    try:
        # Use xpath for text match
        xpath = f"//button[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = '{text.lower()}'] | //a[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = '{text.lower()}']"
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        el.click()
        return True
    except Exception:
        return False

def wait_for_countdown_zero(driver, log_widget, selectors=None, timeout=60):
    """
    Look for common countdown indicators and wait until they reach 0 or become hidden.
    selectors: list of (by, value) tuples to check (optional)
    """
    if selectors is None:
        selectors = [
            (By.ID, "ce-time"),
            (By.ID, "timer"),
            (By.CSS_SELECTOR, "#countdown, .countdown, #ce-wait1"),
            (By.CSS_SELECTOR, "span.timer"),
        ]

    start = time.time()
    while time.time() - start < timeout:
        found_any = False
        for by, val in selectors:
            try:
                elems = driver.find_elements(by, val)
                if not elems:
                    continue
                found_any = True
                for el in elems:
                    try:
                        text = el.text.strip()
                        # Extract digits
                        digits = "".join(ch for ch in text if ch.isdigit() or ch == "-")
                        if digits == "":
                            # maybe innerHTML number?
                            continue
                        try:
                            num = int(digits)
                        except Exception:
                            continue
                        safe_log(log_widget, f"  countdown element '{val}' shows: {num}")
                        if num <= 0:
                            safe_log(log_widget, "  countdown reached 0.")
                            return True
                        # else wait and continue looping
                    except StaleElementReferenceException:
                        continue
            except Exception:
                continue

        if not found_any:
            # no countdown element found -> nothing to wait for
            return False
        time.sleep(1)
    return False

def find_get_link(driver):
    """
    Attempts to find the final 'Get Link' anchor/button and return its href.
    Heuristics:
      - id 'get-link' or 'gt-link'
      - class contains 'get-link'
      - button or anchor text 'Get Link' or 'Get link'
      - any anchor with 'telegram' or 'http' and visible text like 'Get Link'
    """
    # try id
    candidates = []
    try:
        el = driver.find_element(By.ID, "get-link")
        href = el.get_attribute("href")
        if href:
            return href
    except Exception:
        pass
    try:
        el = driver.find_element(By.ID, "gt-link")
        href = el.get_attribute("href")
        if href:
            return href
    except Exception:
        pass

    # class match
    try:
        els = driver.find_elements(By.CSS_SELECTOR, "a.get-link, .get-link, a.btn.get-link")
        for e in els:
            href = e.get_attribute("href")
            if href:
                return href
    except Exception:
        pass

    # text match (anchors or buttons)
    try:
        text_xpath = "//a[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='get link'] | //button[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='get link']"
        els = driver.find_elements(By.XPATH, text_xpath)
        for e in els:
            href = e.get_attribute("href")
            if href:
                return href
            # if button holds a link via onclick, try attribute
            onclick = e.get_attribute("onclick") or ""
            if "http" in onclick:
                # naive extraction
                start = onclick.find("http")
                end = onclick.find("'", start)
                if end == -1:
                    end = onclick.find('"', start)
                if end == -1:
                    end = len(onclick)
                return onclick[start:end]
    except Exception:
        pass

    # look for anchors that look like a final link (telegram / t.me etc)
    try:
        anchors = driver.find_elements(By.TAG_NAME, "a")
        for a in anchors[::-1]:  # search from end
            href = a.get_attribute("href") or ""
            txt = (a.text or "").strip().lower()
            if not href:
                continue
            if "telegram" in href or "t.me" in href or "http" in href:
                # prefer ones with 'get link' text or ones that are visible and non-empty text/href
                if "get link" in txt or txt != "":
                    return href
        # fallback: return first long http(s) anchor
        for a in anchors:
            href = a.get_attribute("href") or ""
            if href.startswith("http") and len(href) > 20:
                return href
    except Exception:
        pass

    return None

def resolve_link_flow(start_url, log_widget, headless=False, max_steps=12):
    """
    Core automation that given a start_url performs the clicking/waiting/redirects
    and returns (final_href, steps_log_list).
    """
    steps = []
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = None
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
    except Exception as e:
        safe_log(log_widget, f"Error starting ChromeDriver: {e}")
        if driver:
            driver.quit()
        return None

    current_url = start_url
    visited = set()
    final_link = None

    try:
        for step in range(max_steps):
            safe_log(log_widget, f"\nStep {step+1}: Opening {current_url}")
            steps.append(("open", current_url))
            try:
                driver.get(current_url)
            except WebDriverException as e:
                safe_log(log_widget, f"  navigation exception: {e}; continuing where possible.")

            time.sleep(1)  # let page settle

            # detect countdown and wait
            countdown_waited = wait_for_countdown_zero(driver, log_widget, timeout=20)
            if countdown_waited:
                safe_log(log_widget, "Countdown handled.")

            # If a Verify button exists, try clicking
            clicked = False
            # Try common selectors (id btn6, verify text)
            if element_click_if_present(driver, By.ID, "btn6", timeout=2):
                safe_log(log_widget, "Clicked element with id 'btn6' (Verify).")
                clicked = True
                steps.append(("click", "btn6"))
                time.sleep(1)
            elif click_button_by_text(driver, "Verify", timeout=2):
                safe_log(log_widget, "Clicked button with text 'Verify'.")
                clicked = True
                steps.append(("click", "verify_text"))
                time.sleep(1)

            # Try Continue link (id btn7 or link text Continue)
            if element_click_if_present(driver, By.ID, "btn7", timeout=2):
                safe_log(log_widget, "Clicked element with id 'btn7' (Continue).")
                clicked = True
                steps.append(("click", "btn7"))
                time.sleep(1)
            elif click_button_by_text(driver, "Continue", timeout=2):
                safe_log(log_widget, "Clicked button/link with text 'Continue'.")
                clicked = True
                steps.append(("click", "continue_text"))
                time.sleep(1)

            # Wait briefly for redirect
            prev_url = current_url
            try:
                # give some time for redirects to happen
                time.sleep(1.5)
                new_url = driver.current_url
                if new_url != prev_url:
                    safe_log(log_widget, f"Redirected: {prev_url} -> {new_url}")
                    current_url = new_url
                    if current_url in visited:
                        safe_log(log_widget, "URL repeated — stopping to avoid infinite loop.")
                        break
                    visited.add(current_url)
                    # check for countdown again on newly loaded page
                    continue
            except Exception:
                pass

            # if nothing clicked and no redirect, maybe there is a "Get Link" on this page
            candidate = find_get_link(driver)
            if candidate:
                final_link = candidate
                safe_log(log_widget, f"Found final link: {final_link}")
                steps.append(("found", final_link))
                break

            # If detect a timer element with id 'timer' showing '0' then wait a bit and search for get link
            try:
                timer_el = driver.find_element(By.ID, "timer")
                timer_text = timer_el.text.strip()
                if timer_text == "0" or timer_text == "":
                    safe_log(log_widget, "Timer is 0 or empty; searching for get link.")
                    candidate = find_get_link(driver)
                    if candidate:
                        final_link = candidate
                        safe_log(log_widget, f"Found final link: {final_link}")
                        steps.append(("found", final_link))
                        break
            except Exception:
                pass

            # In case of no clicks, try to click any link/button that looks like 'Continue' or 'Next' heuristically
            if not clicked:
                # attempt "Next", "Proceed"
                if click_button_by_text(driver, "Next", timeout=1):
                    safe_log(log_widget, "Clicked 'Next' button heuristically.")
                    steps.append(("click", "next_text"))
                    time.sleep(1)
                    continue
                if click_button_by_text(driver, "Proceed", timeout=1):
                    safe_log(log_widget, "Clicked 'Proceed' button heuristically.")
                    steps.append(("click", "proceed_text"))
                    time.sleep(1)
                    continue

            # If still nothing, look for any anchor that looks like a redirect and follow once
            anchors = driver.find_elements(By.TAG_NAME, "a")
            picked = False
            for a in anchors:
                href = a.get_attribute("href") or ""
                txt = (a.text or "").strip().lower()
                if href and ("/readmore" in href or "continue" in href or txt in ("continue", "read more", "get link", "get-link")):
                    safe_log(log_widget, f"Following anchor heuristically: {href} (text='{txt}')")
                    current_url = href
                    steps.append(("heuristic_follow", href))
                    picked = True
                    break
            if picked:
                continue

            # nothing useful found: end loop
            safe_log(log_widget, "No actionable element found on this page. Ending resolution attempts.")
            break

    except Exception as e:
        safe_log(log_widget, f"Exception during flow: {e}\n{traceback.format_exc()}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return final_link

# --------------------------
# Tkinter GUI
# --------------------------
class LinkResolverApp:
    def __init__(self, root):
        self.root = root
        root.title("Link Resolver")
        root.geometry("760x520")

        frm_top = ttk.Frame(root, padding=10)
        frm_top.pack(fill="x")

        ttk.Label(frm_top, text="Start URL:").pack(side="left")
        self.url_var = tk.StringVar()
        self.entry = ttk.Entry(frm_top, textvariable=self.url_var, width=70)
        self.entry.pack(side="left", padx=8)
        self.entry.insert(0, "https://arolinks.com/I5gY8n")  # example

        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm_top, text="Headless", variable=self.headless_var).pack(side="left", padx=6)

        self.start_btn = ttk.Button(frm_top, text="Start Resolve", command=self.on_start)
        self.start_btn.pack(side="left", padx=4)

        frm_mid = ttk.Frame(root, padding=8)
        frm_mid.pack(fill="both", expand=True)

        ttk.Label(frm_mid, text="Log:").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(frm_mid, height=22, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

        frm_bottom = ttk.Frame(root, padding=10)
        frm_bottom.pack(fill="x")
        ttk.Label(frm_bottom, text="Final Link:").pack(side="left")
        self.result_var = tk.StringVar(value="")
        self.result_entry = ttk.Entry(frm_bottom, textvariable=self.result_var, width=80)
        self.result_entry.pack(side="left", padx=6, fill="x", expand=True)

        self.copy_btn = ttk.Button(frm_bottom, text="Copy", command=self.copy_result)
        self.copy_btn.pack(side="left", padx=4)

    def copy_result(self):
        val = self.result_var.get()
        if val:
            self.root.clipboard_clear()
            self.root.clipboard_append(val)
            messagebox.showinfo("Copied", "Final link copied to clipboard.")

    def on_start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a start URL.")
            return
        # disable button
        self.start_btn.config(state="disabled")
        self.log.configure(state="normal")
        self.log.delete("1.0", tk.END)
        self.log.configure(state="disabled")
        self.result_var.set("")

        # run in background thread to keep UI responsive
        thread = threading.Thread(target=self._run_resolve, args=(url, self.headless_var.get()), daemon=True)
        thread.start()

    def _run_resolve(self, url, headless):
        try:
            safe_log(self.log, f"Starting resolution for: {url}")
            result = resolve_link_flow(url, self.log, headless=headless)
            if result:
                safe_log(self.log, f"\n✅ Final extracted link:\n{result}")
                self.result_var.set(result)
            else:
                safe_log(self.log, "\n⚠️ Could not find final 'Get Link' URL.")
        finally:
            self.start_btn.config(state="normal")

def main():
    root = tk.Tk()
    app = LinkResolverApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
