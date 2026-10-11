import unittest
from streamlit.testing.v1 import AppTest

class SidebarTest(unittest.TestCase):
    def test_original_nav_order_and_keys(self):
        import sidebar
        app = AppTest.from_string('import sidebar; sidebar.render(None)').run()
        nav = [b for b in app.button if b.key.startswith('nav_')
               and b.key not in ('nav_logout', 'nav_backup_dialog')]
        self.assertEqual([b.key for b in nav], ['nav_'+k for k in
            ['dashboard','parents','students','teachers','classes','years',
             'registration','payments','salaries','expenses','reports']])
        nav[2].click().run()
        self.assertEqual(app.session_state['current_page'], 'students')
