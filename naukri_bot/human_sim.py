import asyncio
import random
from typing import Tuple, List, Optional
from playwright.async_api import Page, Locator

def calculate_bezier_points(start: Tuple[float, float], end: Tuple[float, float], steps: int = 15) -> List[Tuple[float, float]]:
    """
    Generates a list of coordinates forming a quadratic Bezier curve 
    between start and end coordinates to simulate organic mouse movement.
    """
    x0, y0 = start
    x2, y2 = end
    
    # Calculate a midpoint and add a random offset to create a curved control point P1
    mid_x = (x0 + x2) / 2
    mid_y = (y0 + y2) / 2
    control_offset_x = random.uniform(-100, 100)
    control_offset_y = random.uniform(-100, 100)
    x1 = mid_x + control_offset_x
    y1 = mid_y + control_offset_y

    points = []
    for i in range(steps):
        t = i / (steps - 1)
        # Quadratic Bezier curve equation
        x = (1 - t)**2 * x0 + 2 * (1 - t) * t * x1 + t**2 * x2
        y = (1 - t)**2 * y0 + 2 * (1 - t) * t * y1 + t**2 * y2
        points.append((x, y))
    return points

async def human_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
    """
    Introduces a random sleep/delay between web actions.
    """
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)

async def human_type(locator: Locator, text: str) -> None:
    """
    Types text into an element character-by-character with realistic keyboard delay.
    """
    await locator.focus()
    for char in text:
        await locator.type(char)
        # Keyboard delay typically between 50ms and 150ms
        await asyncio.sleep(random.randint(50, 150) / 1000.0)
    await human_delay(0.2, 0.5)

async def human_mouse_move(page: Page, target_x: float, target_y: float, start_pos: Optional[Tuple[float, float]] = None) -> Tuple[float, float]:
    """
    Moves mouse pointer along a Bezier curve to a target location.
    Returns the target coordinate as the new current position.
    """
    if start_pos is None:
        # Default starting position if not provided (random start)
        start_pos = (random.randint(50, 300), random.randint(50, 300))
        await page.mouse.move(start_pos[0], start_pos[1])

    steps = random.randint(12, 25)
    points = calculate_bezier_points(start_pos, (target_x, target_y), steps=steps)
    
    for x, y in points:
        await page.mouse.move(x, y)
        # Delay between micro-movements
        await asyncio.sleep(random.uniform(0.008, 0.02))
        
    return target_x, target_y

async def human_move_and_click(page: Page, locator: Locator, current_pos: Optional[Tuple[float, float]] = None) -> Tuple[float, float]:
    """
    Moves the cursor organically to a random coordinate inside an element's bounding box and performs a click.
    """
    # Force element to be scrolled into view if needed
    try:
        await locator.scroll_into_view_if_needed()
    except Exception:
        pass
        
    box = await locator.bounding_box()
    if not box:
        # Fallback to direct click if element doesn't have a layout box (hidden or inside scrollables)
        await locator.click()
        return current_pos or (0.0, 0.0)

    # Click in a random inner portion (inset by 20% to avoid edge miss clicks)
    target_x = box["x"] + random.uniform(box["width"] * 0.2, box["width"] * 0.8)
    target_y = box["y"] + random.uniform(box["height"] * 0.2, box["height"] * 0.8)

    # Move mouse
    new_pos = await human_mouse_move(page, target_x, target_y, current_pos)
    await human_delay(0.1, 0.3)

    # Mouse down, hold briefly, and mouse up
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.up()
    
    return new_pos
