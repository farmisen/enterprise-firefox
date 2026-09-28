#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import sys

sys.path.append(os.path.dirname(__file__))

from felt_tests import FeltTests

PORTAL_OVERLAY = ".felt-login__portal"
EMAIL_PANE = ".felt-login__email-pane"


class FeltWindowOpenContainment(FeltTests):
    """
    Test that window.open() from the pre-auth FELT SSO browser cannot produce
    a browser window in the FELT UI process, which runs no enterprise
    policies. The requested URL is shown in the contained pane instead.

    Both forms are covered because they reach the open along different paths:
    a plain open consults nsIBrowserDOMWindow, while one carrying window
    features resolves to OPEN_NEWWINDOW up front unless
    browser.link.open_newwindow.restriction is 0.

    The opens are driven by clicking a button so they carry user activation,
    which keeps the popup blocker from dropping them before they reach
    nsIBrowserDOMWindow.
    """

    def teardown(self):
        # These tests never complete authentication, so there is no child
        # browser to tear down.
        self._manually_closed_child = True
        super().teardown()

    @property
    def _popup_target(self):
        return f"http://localhost:{self.sso_port}/watermark_blank_page"

    def _goto_opener_page(self):
        self.run_felt_chrome_on_email_submit()
        self.run_wait_until_sso_loaded()
        self._driver.set_context("content")
        self._driver.navigate(f"http://localhost:{self.sso_port}/popup_opener")
        self._wait.until(
            lambda mn: mn.get_url().endswith("/popup_opener"),
            message="The opener page loads in the SSO browser",
        )

    def _pane_state(self):
        self._driver.set_context("chrome")
        return self._driver.execute_script(
            """
            const pane = document.querySelector(arguments[0]);
            const browser = document.getElementById("portal-browser");
            return {
              shown: !pane.classList.contains("is-hidden"),
              url: browser && browser.currentURI ? browser.currentURI.spec : null,
            };
            """,
            [PORTAL_OVERLAY],
        )

    def _assert_contained_in_pane(self):
        self._wait.until(
            lambda _: self._pane_state()["url"] == self._popup_target,
            message="The requested URL is shown in the contained pane",
        )
        state = self._pane_state()
        assert state["shown"], "The contained pane is visible"
        assert len(self._driver.chrome_window_handles) == 1, (
            "No browser window is opened in the FELT UI process"
        )

    def test_plain_window_open_is_contained(self):
        self._goto_opener_page()
        self.get_elem("#open-plain").click()
        self._assert_contained_in_pane()
        self._driver.set_context("content")

    def test_featured_window_open_is_contained(self):
        self._goto_opener_page()
        self.get_elem("#open-features").click()
        self._assert_contained_in_pane()
        self._driver.set_context("content")

    def test_back_button_after_captive_portal_teardown(self):
        # CaptivePortal hides the shared pane without going through
        # closePane(), so the back button must still reset the login flow
        # rather than spend the click closing an already-hidden pane.
        self._goto_opener_page()
        self.get_elem("#open-plain").click()
        self._assert_contained_in_pane()

        self._driver.set_context("chrome")
        self._driver.execute_script(
            "Services.obs.notifyObservers(null, arguments[0]);",
            ["captive-portal-login-abort"],
        )
        self._wait.until(
            lambda _: not self._pane_state()["shown"],
            message="The captive-portal teardown hides the pane",
        )

        self._driver.set_context("chrome")
        self.get_elem("#felt-back-button").click()
        self._wait.until(
            lambda _: self.find_elem(EMAIL_PANE).is_displayed(),
            message="Back returns to the email pane on the first click",
        )
        self._driver.set_context("content")
