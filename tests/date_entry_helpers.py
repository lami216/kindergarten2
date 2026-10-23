"""Fill the visible date controls, preserving the same browser behavior as the user."""


async def fill_field(locator, value):
    if await locator.get_attribute('data-date-canonical') is None:
        await locator.fill(value)
        return
    group = locator.locator('xpath=preceding-sibling::*[1]')
    bits = value.split('-') if value else ['', '', '']
    await group.locator('[data-date-part="month"]').select_option(bits[1])
    day = group.locator('[data-date-part="day"]')
    if await day.count():
        await day.fill(bits[2])
    year = group.locator('[data-date-part="year"]')
    await year.fill(bits[0][-2:])
    await year.press('Tab')
