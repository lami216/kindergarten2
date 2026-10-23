"""Synthetic package compatibility fixture; never a user-facing app route."""
import io
import zipfile
from PIL import Image
from reportlab.pdfgen import canvas
import streamlit as st

picture = io.BytesIO()
Image.new('RGB', (80, 60), 'teal').save(picture, format='PNG')
st.image(picture.getvalue())
archive = io.BytesIO()
with zipfile.ZipFile(archive, 'w') as z:
    z.writestr('synthetic.txt', 'package-response-check')
st.download_button('ZIP compatibility', archive.getvalue(), 'synthetic.zip', 'application/zip')
pdf = io.BytesIO()
document = canvas.Canvas(pdf)
document.drawString(30, 700, 'Synthetic dependency check: 1200 MRO')
document.save()
st.download_button('PDF compatibility', pdf.getvalue(), 'synthetic.pdf', 'application/pdf')
