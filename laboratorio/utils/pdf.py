import asyncio
from pyppeteer import launch
from django.template.loader import render_to_string
from django.conf import settings
import os

CHROME_ARGS = [
    '--no-sandbox',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    '--disable-setuid-sandbox',
    '--disable-web-security'
]

async def _render_pdf(html_content, output_path):
    browser = await launch(args=CHROME_ARGS)
    page = await browser.newPage()
    await page.setContent(html_content, waitUntil='networkidle0')

    await page.pdf({
        'path': output_path,
        'format': 'A4',
        'printBackground': True,
        'margin': {
            'top': '14mm',
            'bottom': '14mm',
            'left': '12mm',
            'right': '12mm'
        }
    })

    await browser.close()


def html_to_pdf(template_name, context, output_filename="documento.pdf"):
    html = render_to_string(template_name, context)

    output_path = os.path.join(settings.MEDIA_ROOT, output_filename)

    asyncio.get_event_loop().run_until_complete(
        _render_pdf(html, output_path)
    )

    return output_path
