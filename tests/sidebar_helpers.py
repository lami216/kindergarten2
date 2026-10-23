"""Interact with actual sidebar state across Streamlit DOM versions."""
from playwright.async_api import expect


async def sidebar_collapsed(page, navigation):
    sidebar = page.locator('[data-testid="stSidebar"]')
    state = await sidebar.get_attribute('data-collapsed')
    if state is not None:
        return state == 'true'
    return not await navigation.is_visible()


async def collapse_sidebar(page):
    sidebar = page.locator('[data-testid="stSidebar"]')
    if await sidebar.get_attribute('data-collapsed') == 'true':
        return  # Navigation may already have collapsed it on mobile.
    await sidebar.hover()  # Newer Streamlit reveals the control on hover.
    button = page.get_by_role('button', name='Collapse sidebar', exact=True)
    await expect(button).to_be_visible()
    await button.click()
    if await sidebar.get_attribute('data-collapsed') is not None:
        await expect(sidebar).to_have_attribute('data-collapsed', 'true')
