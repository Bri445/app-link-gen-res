import streamlit as st
import time
import traceback

# Selenium imports
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import *
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ---------------------------------------------------
# Logging utility
# ---------------------------------------------------
def log(msg):
    st.session_state["log"].append(msg)
    st.write(msg)


# ---------------------------------------------------
# Start Chrome for Streamlit Cloud
# ---------------------------------------------------
def start_driver():
    chromedriver_autoinstaller.install()  # auto install the correct chromedriver

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------
def wait_for_countdown(driver):
    """wait until timer ce-time or timer id reaches 0"""
    ids = ["ce-time", "timer"]
    start = time.time()
    while time.time() - start < 40:
        found = False
        for cid in ids:
            try:
                el = driver.find_element(By.ID, cid)
                txt = el.text.strip()
                if txt.isdigit():
                    log(f"⏳ Countdown: {txt}")
                    if int(txt) <= 0:
                        log("⏳ Countdown reached 0.")
                        return
                found = True
            except:
                pass
        if not found:
            return
        time.sleep(1)


def click_buttons(driver):
    """Try verify & continue buttons"""
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
            time.sleep(1.2)
            return True
        except:
            pass

    for txt in texts:
        try:
            btn = driver.find_element(By.XPATH, f"//*[text()='{txt}']")
            btn.click()
            log(f"🔘 Clicked button: {txt}")
            time.sleep(1.2)
            return True
        except:
            pass

    return False


def find_final_link(driver):
    """Extract 'Get Link' button href"""
    try:
        el = driver.find_element(By.ID, "get-link")
        href = el.get_attribute("href")
        return href
    except:
        pass

    anchors = driver.find_elements(By.TAG_NAME, "a")
    for a in anchors:
        href = a.get_attribute("href") or ""
        if "telegram" in href or "http" in href:
            if "get" in a.text.lower():
                return href
    return None


# ---------------------------------------------------
# Core automation flow
# ---------------------------------------------------
def resolve(start_url):
    driver = start_driver()
    current = start_url

    try:
        for step in range(12):
            log(f"\n### Step {step+1}: Opening {current}")

            try:
                driver.get(current)
            except:
                log("⚠️ Navigation error, continuing...")

            time.sleep(2)

            wait_for_countdown(driver)

            clicked = click_buttons(driver)

            time.sleep(1.5)

            # detect redirect
            new_url = driver.current_url
            if new_url != current:
                log(f"➡️ Redirected to: {new_url}")
                current = new_url

            # find final link
            final = find_final_link(driver)
            if final:
                log("🎉 FINAL LINK FOUND:")
                log(final)
                return final

        return None

    except Exception as e:
        log(f"❌ Error: {e}")
        log(traceback.format_exc())
        return None

    finally:
        driver.quit()


# ---------------------------------------------------
# Streamlit UI
# ---------------------------------------------------
st.set_page_config(page_title="Auto Link Resolver", layout="wide")
st.title("🔗 Auto Link Resolver (Selenium + Streamlit)")

if "log" not in st.session_state:
    st.session_state["log"] = []

url = st.text_input("Enter AroLinks URL:", placeholder="https://arolinks.com/XXXXX")

if st.button("Start"):
    st.session_state["log"] = []

    if not url.strip():
        st.error("Enter a valid URL.")
    else:
        st.write("⚙️ Running automation... please wait 10–20 seconds ⏳")
        output = resolve(url)

        if output:
            st.success("Final Link:")
            st.code(output)
        else:
            st.error("Could not fetch final link.")

st.write("### 📜 Logs:")
for line in st.session_state["log"]:
    st.write(line)

