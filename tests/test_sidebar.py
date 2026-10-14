import unittest
from streamlit.testing.v1 import AppTest

class SidebarTest(unittest.TestCase):
    def test_daily_nav_before_finance_and_school_files(self):
        import sidebar
        app = AppTest.from_string('import sidebar; sidebar.render(None)').run()
        nav = [b for b in app.button if b.key.startswith('nav_')
               and b.key not in ('nav_logout', 'nav_backup_dialog')]
        self.assertEqual([b.key for b in nav], ['nav_'+k for k in
            ['dashboard','students','registration','payments','expenses',
             'reports','salaries','parents','teachers','classes','years']])
        nav[1].click().run()
        self.assertEqual(app.session_state['current_page'], 'students')
