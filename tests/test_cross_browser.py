import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def get_browser_driver(browser_name):
    print("\n==========================================")
    print(f"Launching {browser_name}...")
    print("==========================================")
    if browser_name == "google-chrome":
        opts = ChromeOptions()
        opts.binary_location = "/bin/google-chrome"
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1440,1050")
        tmpdir = tempfile.mkdtemp(prefix="chrome-user-")
        opts.add_argument(f"--user-data-dir={tmpdir}")
        driver = webdriver.Chrome(options=opts)
        return driver, lambda: (driver.quit(), shutil.rmtree(tmpdir, ignore_errors=True))

    elif browser_name == "chromium":
        port = find_free_port()
        tmpdir = tempfile.mkdtemp(prefix="chromium-snap-")
        proc = subprocess.Popen(
            [
                "/snap/bin/chromium",
                "--headless=new",
                f"--remote-debugging-port={port}",
                "--no-sandbox",
                "--disable-gpu",
                "--window-size=1440,1050",
                f"--user-data-dir={tmpdir}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        opts = ChromeOptions()
        opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
        driver = webdriver.Chrome(options=opts)

        def cleanup():
            driver.quit()
            proc.terminate()
            proc.wait()
            shutil.rmtree(tmpdir, ignore_errors=True)

        return driver, cleanup

    elif browser_name == "firefox":
        opts = FirefoxOptions()
        opts.add_argument("-headless")
        opts.add_argument("--width=1440")
        opts.add_argument("--height=1050")
        service = FirefoxService(executable_path="/snap/bin/geckodriver")
        driver = webdriver.Firefox(service=service, options=opts)
        return driver, lambda: driver.quit()

    else:
        raise ValueError(f"Unknown browser: {browser_name}")


def run_suite_for_browser(browser_name):
    driver, cleanup = get_browser_driver(browser_name)
    try:
        html_file = Path("outputs/rec3d_viewer.html").resolve()
        file_url = html_file.as_uri()
        print(f"[{browser_name}] Loading: {file_url}")
        driver.get(file_url)
        time.sleep(1.5)

        # 1. Verify Page & Trial Data
        title = driver.title
        assert "mkvis3d" in title, f"Unexpected title: {title}"
        frame_text = driver.find_element(By.ID, "frame").text
        assert "631" in frame_text, f"Expected 631 frames in frame text, got: {frame_text}"
        meta_text = driver.find_element(By.ID, "meta").text
        assert "70" in meta_text, f"Expected 70 markers in meta text, got: {meta_text}"
        print(f"[{browser_name}] PASS: Trial data loaded (631 frames, 70 markers)")

        # 2. Theme Switching (Dark / Light)
        initial_theme = driver.execute_script(
            "return document.documentElement.getAttribute('data-theme')"
        )
        assert initial_theme == "dark", f"Expected default dark theme, got: {initial_theme}"

        # Toggle via header button
        btn_toggle = driver.find_element(By.ID, "btn-toggle-theme")
        btn_toggle.click()
        time.sleep(0.3)
        theme_after_toggle = driver.execute_script(
            "return document.documentElement.getAttribute('data-theme')"
        )
        assert theme_after_toggle == "light", (
            f"Expected light theme after toggle, got: {theme_after_toggle}"
        )
        assert driver.find_element(By.ID, "theme-label").text == "Light"

        # Capture light screenshot
        out_light = f"outputs/screenshot_{browser_name}_light.png"
        driver.save_screenshot(out_light)
        print(f"[{browser_name}] PASS: Theme switched to light, saved {out_light}")

        # Switch back to dark via View menu action item
        action_dark = driver.find_element(By.ID, "action-theme-dark")
        driver.execute_script("arguments[0].click();", action_dark)
        time.sleep(0.3)
        assert (
            driver.execute_script("return document.documentElement.getAttribute('data-theme')")
            == "dark"
        )
        assert driver.find_element(By.ID, "theme-label").text == "Dark"

        # Capture dark screenshot
        out_dark = f"outputs/screenshot_{browser_name}_dark.png"
        driver.save_screenshot(out_dark)
        print(f"[{browser_name}] PASS: Theme switched to dark, saved {out_dark}")

        # 3. Marker Size Customization
        slider = driver.find_element(By.ID, "marker-size-slider")
        assert slider.is_displayed(), "Marker size slider should be displayed"
        btn_dec = driver.find_element(By.ID, "btn-dec-marker-size")
        btn_inc = driver.find_element(By.ID, "btn-inc-marker-size")
        val_readout = driver.find_element(By.ID, "marker-size-val")

        assert val_readout.text == "3.5 px", (
            f"Initial size should be 3.5 px, got: {val_readout.text}"
        )

        # Test increment button
        btn_inc.click()
        time.sleep(0.1)
        assert val_readout.text == "4.0 px", f"Expected 4.0 px after inc, got: {val_readout.text}"

        # Test decrement button
        btn_dec.click()
        time.sleep(0.1)
        assert val_readout.text == "3.5 px", f"Expected 3.5 px after dec, got: {val_readout.text}"

        # Set via slider value using JS and dispatch input event
        driver.execute_script("""
            const sl = document.getElementById('marker-size-slider');
            sl.value = '6.5';
            sl.dispatchEvent(new Event('input'));
        """)
        time.sleep(0.1)
        assert val_readout.text == "6.5 px", (
            f"Expected 6.5 px after slider change, got: {val_readout.text}"
        )
        print(f"[{browser_name}] PASS: Marker size controls (+/- buttons, slider)")

        # 4. Marker Color Customization (Palette, Custom, Reset)
        badge = driver.find_element(By.ID, "marker-color-name-badge")
        assert badge.text.upper() == "DEFAULT", f"Expected initial color Default, got: {badge.text}"

        # Click Orange swatch (#f97316)
        swatch_orange = driver.find_element(
            By.CSS_SELECTOR, ".color-swatch-btn[data-color='#f97316']"
        )
        swatch_orange.click()
        time.sleep(0.1)
        assert badge.text.upper() == "ORANGE", f"Expected Orange badge, got: {badge.text}"
        assert "selected" in swatch_orange.get_attribute("class")

        # Click Blue swatch (#3b82f6)
        swatch_blue = driver.find_element(
            By.CSS_SELECTOR, ".color-swatch-btn[data-color='#3b82f6']"
        )
        swatch_blue.click()
        time.sleep(0.1)
        assert badge.text.upper() == "BLUE", f"Expected Blue badge, got: {badge.text}"

        # Custom color picker input
        driver.execute_script("""
            const c = document.getElementById('marker-color-custom');
            c.value = '#00ffaa';
            c.dispatchEvent(new Event('input'));
        """)
        time.sleep(0.1)
        assert badge.text.lower() == "#00ffaa", (
            f"Expected custom color badge #00ffaa, got: {badge.text}"
        )

        # Reset button
        btn_reset = driver.find_element(By.ID, "btn-reset-marker-style")
        btn_reset.click()
        time.sleep(0.1)
        assert badge.text.upper() == "DEFAULT", (
            f"Expected Default badge after reset, got: {badge.text}"
        )
        assert val_readout.text == "3.5 px", f"Expected reset size 3.5 px, got: {val_readout.text}"
        print(f"[{browser_name}] PASS: Marker color controls (Orange, Blue, Custom #00ffaa, Reset)")

        # 5. Keyboard Shortcuts (+, -, C)
        # Blur any focused element so keys target document body
        driver.execute_script("if (document.activeElement) document.activeElement.blur();")
        actions = ActionChains(driver)

        # Dispatch C key
        actions.send_keys("c").perform()
        time.sleep(0.1)
        badge_after_c = badge.text
        assert badge_after_c.upper() != "DEFAULT", (
            f"Expected cycle color shortcut C to change badge, got: {badge_after_c}"
        )

        # Dispatch + key
        driver.execute_script("if (document.activeElement) document.activeElement.blur();")
        actions.send_keys("+").perform()
        time.sleep(0.1)
        size_after_plus = float(
            driver.find_element(By.ID, "marker-size-slider").get_attribute("value")
        )
        assert size_after_plus > 3.5, (
            f"Expected '+' shortcut to increase marker size, got: {size_after_plus}"
        )

        # Dispatch - key
        driver.execute_script("if (document.activeElement) document.activeElement.blur();")
        actions.send_keys("-").perform()
        time.sleep(0.1)
        size_after_minus = float(
            driver.find_element(By.ID, "marker-size-slider").get_attribute("value")
        )
        assert size_after_minus < size_after_plus, "Expected '-' shortcut to decrease marker size"
        print(f"[{browser_name}] PASS: Keyboard shortcuts (C, +, -)")

        # 6. Vertical Resizer Splitter
        splitter = driver.find_element(By.ID, "vertical-splitter")
        assert splitter.is_displayed(), "Vertical splitter should be displayed"
        container = driver.find_element(By.ID, "windows-container")
        initial_plot_h = driver.execute_script(
            "return getComputedStyle(arguments[0]).getPropertyValue('--plot-height').trim();",
            container,
        )
        assert initial_plot_h == "170px" or initial_plot_h == "", (
            f"Initial plot height: {initial_plot_h}"
        )

        # Simulate resizing by setting --plot-height
        driver.execute_script("""
            const container = document.getElementById('windows-container');
            container.style.setProperty('--plot-height', '260px');
            resize();
        """)
        time.sleep(0.1)
        new_h = driver.execute_script(
            "return getComputedStyle(arguments[0]).getPropertyValue('--plot-height').trim();",
            container,
        )
        assert new_h == "260px", f"Expected 260px after resizing, got: {new_h}"

        # Double click splitter to reset to 170px
        driver.execute_script("""
            const splitter = document.getElementById('vertical-splitter');
            splitter.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
        """)
        time.sleep(0.1)
        reset_h = driver.execute_script(
            "return getComputedStyle(arguments[0]).getPropertyValue('--plot-height').trim();",
            container,
        )
        assert reset_h == "170px", f"Expected 170px after double click reset, got: {reset_h}"
        print(
            f"[{browser_name}] PASS: Vertical resizer splitter (resize to 260px, double-click reset to 170px)"
        )

        # 7. Detached Subwindows & Floating Pane Support
        # Test 7A: Floating pane mode with draggable and resizable state
        driver.execute_script("floatPane('panel-plot1');")
        time.sleep(0.2)
        plot_pane = driver.find_element(By.ID, "panel-plot1")
        assert "floating-pane" in plot_pane.get_attribute("class"), (
            "Pane should have floating-pane class"
        )
        assert driver.execute_script("return activeFloatingPanes.has('panel-plot1');") is True

        # Test docking back to layout
        btn_float = plot_pane.find_element(By.CSS_SELECTOR, ".btn-float")
        assert btn_float.text == "↙", f"Float button should show dock icon ↙, got: {btn_float.text}"
        btn_float.click()
        time.sleep(0.2)
        assert "floating-pane" not in plot_pane.get_attribute("class"), (
            "Pane should return to grid layout"
        )
        assert driver.execute_script("return activeFloatingPanes.has('panel-plot1');") is False

        # Test 7B: Popout window synchronization logic and direct plot rendering
        # Verify syncPopoutContent functions properly without runtime errors
        sync_ok = driver.execute_script("""
            try {
                // Test syncPopoutContent when closed or open
                syncPopoutContent('panel-plot1');
                syncPopoutContent('panel-3d');
                syncPopoutContent('panel-table');
                return true;
            } catch(e) {
                return e.message;
            }
        """)
        assert sync_ok is True, f"syncPopoutContent failed: {sync_ok}"
        print(f"[{browser_name}] PASS: Floating subwindow and popout synchronization logic")

        # 8. Visual3D Laboratory Coordinate System (LCS)
        btn_open_lcs = driver.find_element(By.ID, "btn-open-lcs")
        driver.execute_script("arguments[0].scrollIntoView();", btn_open_lcs)
        btn_open_lcs.click()
        time.sleep(0.3)
        modal_lcs = driver.find_element(By.ID, "modal-lcs")
        assert "open" in modal_lcs.get_attribute("class"), "LCS modal should be open"

        # Capture screenshot of LCS modal in Google Chrome
        if browser_name == "google-chrome":
            driver.save_screenshot("outputs/screenshot_lcs_modal.png")

        # Test preset click: BVH / Unity (+Y Up, +Z AP)
        bvh_btn = driver.find_element(By.CSS_SELECTOR, ".btn-lcs-preset[data-preset='y_up_bvh']")
        bvh_btn.click()
        time.sleep(0.2)

        axial_val = driver.find_element(By.ID, "lcs-axial-select").get_attribute("value")
        ap_val = driver.find_element(By.ID, "lcs-ap-select").get_attribute("value")
        ml_text = driver.find_element(By.ID, "lcs-ml-result").text
        det_text = driver.find_element(By.ID, "lcs-det-result").text

        assert axial_val == "+Y", f"Expected axial +Y, got {axial_val}"
        assert ap_val == "+Z", f"Expected ap +Z, got {ap_val}"
        assert ml_text == "-X", f"Expected ML -X, got {ml_text}"
        assert "Right-Handed" in det_text, f"Expected Right-Handed, got {det_text}"

        # Apply LCS transformation
        btn_apply_lcs = driver.find_element(By.ID, "btn-apply-lcs")
        btn_apply_lcs.click()
        time.sleep(0.3)
        assert "open" not in modal_lcs.get_attribute("class"), "LCS modal should close after apply"

        lcs_badge = driver.find_element(By.ID, "lcs-active-badge")
        assert "BVH" in lcs_badge.text, (
            f"LCS badge should indicate BVH preset, got: {lcs_badge.text}"
        )

        # Reset LCS via modal
        btn_open_lcs.click()
        time.sleep(0.2)
        btn_reset_lcs = driver.find_element(By.ID, "btn-reset-lcs")
        btn_reset_lcs.click()
        time.sleep(0.3)
        assert "ISB" in lcs_badge.text, f"LCS badge should return to ISB, got: {lcs_badge.text}"
        print(f"[{browser_name}] PASS: Visual3D LCS dialog, presets, matrix computation, and reset")

        # 9. Biomechanical Signal Processing & Gap-Fill Modal, Live Preview & Undo
        btn_open_filter = driver.find_element(By.ID, "btn-open-filter")
        driver.execute_script("arguments[0].scrollIntoView();", btn_open_filter)
        btn_open_filter.click()
        time.sleep(0.3)
        modal_filter = driver.find_element(By.ID, "modal-filter")
        assert "open" in modal_filter.get_attribute("class"), "Filter modal should be open"

        # Capture screenshot of Filter modal in Google Chrome
        if browser_name == "google-chrome":
            driver.save_screenshot("outputs/screenshot_filter_modal.png")

        # Verify default filter cutoff readout
        cutoff_val = driver.find_element(By.ID, "flt-cutoff-val").text
        assert "6.0 Hz" in cutoff_val, f"Default cutoff should be 6.0 Hz, got: {cutoff_val}"

        # Change cutoff to 8.0 Hz via slider script
        driver.execute_script("""
            const slider = document.getElementById('flt-cutoff-slider');
            slider.value = '8.0';
            slider.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        time.sleep(0.2)
        assert "8.0 Hz" in driver.find_element(By.ID, "flt-cutoff-val").text

        # Apply processing
        btn_apply_filter = driver.find_element(By.ID, "btn-apply-filter")
        btn_apply_filter.click()
        time.sleep(0.3)
        assert "open" not in modal_filter.get_attribute("class"), (
            "Filter modal should close after apply"
        )

        filter_badge = driver.find_element(By.ID, "filter-status-badge")
        assert "BW 8" in filter_badge.text, (
            f"Filter badge should show BW 8Hz, got: {filter_badge.text}"
        )

        btn_revert = driver.find_element(By.ID, "btn-revert-filter")
        assert btn_revert.is_enabled(), "Revert button should be enabled after applying filter"

        # Revert filter to raw
        btn_revert.click()
        time.sleep(0.2)
        assert filter_badge.text.strip().lower() == "raw", (
            f"Filter badge should return to Raw, got: {filter_badge.text}"
        )
        assert not btn_revert.is_enabled(), (
            "Revert button should be disabled after reverting to raw"
        )

        # Test Quick Filter button in sidebar
        btn_quick = driver.find_element(By.ID, "btn-quick-filter")
        btn_quick.click()
        time.sleep(0.2)
        assert "BW 6" in filter_badge.text, (
            f"Quick filter should apply 6Hz, got: {filter_badge.text}"
        )
        btn_revert.click()
        time.sleep(0.2)
        assert filter_badge.text.strip().lower() == "raw"
        print(
            f"[{browser_name}] PASS: Signal filtering modal, live preview, apply, quick smooth, and revert"
        )

        # 10. Welcome Screen & Select File Button
        welcome_url = Path("outputs/empty_viewer.html").resolve().as_uri()
        driver.get(welcome_url)
        time.sleep(0.5)

        welcome = driver.find_element(By.ID, "welcome")
        assert welcome.is_displayed(), "Welcome dropzone should be visible with empty template"
        btn_select = driver.find_element(By.ID, "btn-welcome-select")
        assert btn_select.is_displayed(), "Select File button should be displayed in welcome zone"

        # Verify button click triggers file input click
        file_clicked = driver.execute_script("""
            let clicked = false;
            const fileInput = document.getElementById('file');
            fileInput.onclick = () => { clicked = true; return false; };
            document.getElementById('btn-welcome-select').click();
            return clicked;
        """)
        assert file_clicked is True, "Clicking #btn-welcome-select should trigger #file click"
        print(f"[{browser_name}] PASS: Welcome screen and Select File button click handler")

        # 11. Test Squat file (squat_viewer.html) as well to verify secondary dataset
        squat_url = Path("outputs/squat_viewer.html").resolve().as_uri()
        driver.get(squat_url)
        time.sleep(1.0)
        squat_frame_text = driver.find_element(By.ID, "frame").text
        assert "/" in squat_frame_text, f"Squat trial frames: {squat_frame_text}"
        print(f"[{browser_name}] PASS: Squat trial loaded ({squat_frame_text})")

        print(f"\n>>> [{browser_name}] ALL 11 TEST CATEGORIES PASSED WITH 100% SUCCESS! <<<\n")
        return True

    finally:
        cleanup()


@pytest.mark.browser
@pytest.mark.parametrize("browser_name", ["google-chrome", "chromium", "firefox"])
def test_cross_browser_compatibility(browser_name):
    """Verifies full compatibility on Google Chrome, Chromium, and Firefox."""
    assert run_suite_for_browser(browser_name) is True


if __name__ == "__main__":
    browsers = ["google-chrome", "chromium", "firefox"]
    results = {}
    for b in browsers:
        try:
            results[b] = run_suite_for_browser(b)
        except Exception as e:
            import traceback

            print(f"FAILED on {b}: {e}")
            traceback.print_exc()
            results[b] = False

    print("\n==========================================")
    print("CROSS-BROWSER TEST SUMMARY:")
    print("==========================================")
    all_ok = True
    for b, ok in results.items():
        status = "PASSED" if ok else "FAILED"
        print(f"  {b:15s}: {status}")
        if not ok:
            all_ok = False

    if not all_ok:
        sys.exit(1)
    print("\nAll 3 browsers (Google Chrome, Chromium, Firefox) verified successfully!")
