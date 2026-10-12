import unittest
from streamlit.testing.v1 import AppTest

class ThemeControlTest(unittest.TestCase):
    def test_night_mode_survives_navigation_reruns(self):
        app = AppTest.from_string("""
import style
import streamlit as st
style.apply_style()
st.button("rerun")
""").run(timeout=20)
        self.assertEqual([t.label for t in app.toggle], ["الوضع الليلي"])
        app.toggle[0].set_value(True).run()
        self.assertTrue(app.session_state['night_mode'])
        app.button[0].click().run()
        self.assertTrue(app.toggle[0].value)
        self.assertTrue(any('#101519' in m.value for m in app.markdown))
