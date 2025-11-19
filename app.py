import streamlit as st
import time
import traceback
from urllib.parse import urlparse

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import *
from webdriver_manager.chrome import ChromeDriverManager


# ------------------------------------
# Helper logging to the UI
# ------------------------------------
def log(msg):
    st.session_state["log"].append(msg)
    st.write(msg)


# Wait for countdown elements
def wait_for_countdown(driver):
    possible_ids = ["ce-time", "timer"]
    start = time.time()
    while time.time() - start < 60:
        found = False
        for cid in possible_ids:
            try:
                el = driver.find_element(By.ID, cid)
                txt = el.text.strip()
                if txt.isdigit() and int(txt) <= 0:
                    log("⏳ Countdown reached 0.")
                    return
                found = True
            except:
                pass
        if not found:
            return  # no countdown found
        time.sleep(1)


# Try to click buttons by IDs/text
def click_if_exists(driver):
    selectors = [
        (By.ID, "btn6"),  # Verify
        (By.ID, "btn7"),  # Continue
    ]
    texts = ["Verify", "Continue"]

    for by, val in selectors:
        try:
            btn = driver.find_element(by, val)
            btn.click()
            log(f"🔘 Clicked button: {val}")
            time.sleep(1)
            return True
        except:
            pass

    for txt in texts:
        try:
            btn = driver.find_element(By.XPATH, f"//*[text()='{txt}']")
            btn.click()
            log(f"🔘 Clicked button: {txt}")
            time.sleep(1)
            return True
        except:
            pass

    return False


# find final "Get Link"
def find_final_link(driver):
    try:
        el = driver.find_element(By.ID, "get-link")
        href = el.get_attribute("href")
        return href
    except:
        pass

    anchors = driver.find_elements(By.TAG_NAME, "a")
    for a in anchors:
        href = a.get_attribute("href")
        if href and ("telegram" in href or "http" in href):
            if "get" in a.text.lower():
                return href

    return None


# ------------------------------------
# Core Selenium flow for Streamlit
# ------------------------------------
def resolve_link(start_url):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Start Chrome
    driver = webdriver.Chrome(
        ChromeDriverManager().install(),
        options=chrome_options,
    )

    current = start_url

    try:
        for step in range(10):
            log(f"\n### Step {step+1}: Opening {current}")
            driver.get(current)
            time.sleep(2)

            # Wait for countdown
            wait_for_countdown(driver)

            # Try clicking verify/continue
            clicked = click_if_exists(driver)

            # After clicking, wait a bit
            time.sleep(1.8)

            new_url = driver.current_url
            if new_url != current:
                log(f"➡️ Redirected to: {new_url}")
                current = new_url

            # Try to find final link
            final_link = find_final_link(driver)
            if final_link:
                log(f"🎉 ### FINAL LINK FOUND:\n{final_link}")
                return final_link

        return None

    except Exception as e:
        log(f"Error: {e}")
        log(traceback.format_exc())
        return None

    finally:
        driver.quit()


# ------------------------------------
# Streamlit UI
# ------------------------------------
st.title("🔗 Auto Link Resolver (Streamlit + Selenium)")
st.write("Paste your AroLinks URL and this tool will auto-click, wait, and extract the final link.")

if "log" not in st.session_state:
    st.session_state["log"] = []

url = st.text_input("Enter link:", placeholder="https://arolinks.com/XXXXX")

if st.button("Start"):
    st.session_state["log"] = []
    if url.strip() == "":
        st.error("Enter a valid link.")
    else:
        st.write("Running automation... please wait 10–20 seconds ⏳")

        final = resolve_link(url)

        if final:
            st.success("Final Link:")
            st.code(final)
        else:
            st.error("Could not extract final link.")

# Show logs
st.write("### Logs:")
for line in st.session_state["log"]:
    st.write(line)
