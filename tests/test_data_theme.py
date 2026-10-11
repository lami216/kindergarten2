import unittest
from streamlit.testing.v1 import AppTest

class DataThemeTest(unittest.TestCase):
    def test_dataframe_dark_cells_keep_values_columns_and_native_export(self):
        app = AppTest.from_string("""
import ui, streamlit as st, pandas as pd
st.session_state.night_mode = True
ui.dataframe(pd.DataFrame({'اسم':['اختبار'], 'المبلغ':[1250]}), hide_index=True)
""").run(timeout=15)
        self.assertEqual(len(app.exception), 0)
        self.assertIn('background-color: #202223', app.dataframe[0].proto.arrow_data.styler.styles)
        self.assertEqual(app.dataframe[0].value.iloc[0].tolist(), ['اختبار', 1250])

    def test_chart_dark_surface_does_not_change_values(self):
        import json
        app = AppTest.from_string("""
import ui, streamlit as st
import plotly.graph_objects as go
st.session_state.night_mode = True
ui.plotly_chart(go.Figure(go.Bar(x=['اختبار'], y=[1250])))
""").run(timeout=15)
        self.assertEqual(len(app.exception), 0)
        spec = json.loads(app.get('plotly_chart')[0].proto.spec)
        self.assertEqual(spec['layout'].get('paper_bgcolor'), '#202223')
        self.assertEqual(spec['data'][0]['y'], [1250])

    def test_all_sections_use_theme_renderers(self):
        import ast
        from pathlib import Path
        for path in (Path(__file__).resolve().parents[1] / 'sections').glob('*.py'):
            tree = ast.parse(path.read_text())
            direct = [n.func.attr for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == 'st'
                and n.func.attr in ('dataframe','plotly_chart')]
            self.assertEqual(direct, [], path.name)
