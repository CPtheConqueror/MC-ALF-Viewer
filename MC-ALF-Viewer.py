"""
Infdev / Alpha World Map Viewer
================================
Uses the Alpha level format: individual gzipped NBT .dat chunk files stored
in base36-named subdirectories. This format was used from Infdev 20100327
through approximately Beta 1.2_02, before Mojang switched to McRegion (.mcr)
in Beta 1.3.

Features:
  - Main menu: choose map render or block search, loops until you quit
  - Flat map: colour-coded top-down view (gridless + grid versions)
  - Shaded map: same but shaded by elevation like Minecraft's in-game map
    (gridless + grid versions)
  - Block search: find any block ID across all chunks, export to txt if many

Requirements (installed automatically):
  nbtlib, Pillow
"""

import sys
import io
import re
import zlib
import gzip
import argparse
import tkinter as tk
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency check / auto-install
# ---------------------------------------------------------------------------
def ensure_deps():
    import importlib, subprocess
    for pkg, import_name in [("nbtlib", "nbtlib"), ("Pillow", "PIL")]:
        try:
            importlib.import_module(import_name)
        except ImportError:
            print(f"[setup] Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

ensure_deps()

import nbtlib                                        # type: ignore
from PIL import Image, ImageDraw, ImageFont          # type: ignore

# Matches chunk filenames: c.0.0.dat  c.-4.-4.dat  c.1a.-z.dat etc.
CHUNK_FILENAME_RE = re.compile(r'^c\.(-?[0-9a-z]+)\.(-?[0-9a-z]+)\.dat$', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Block colour table — every block through Beta 1.2_02
# ---------------------------------------------------------------------------
BLOCK_COLOURS = {
    0:  ( 30,  30,  30),  # Air
    1:  (136, 136, 136),  # Stone
    2:  ( 90, 140,  60),  # Grass
    3:  (134,  96,  67),  # Dirt
    4:  (155, 155, 155),  # Cobblestone
    5:  (180, 140,  80),  # Wood Planks
    6:  ( 60, 120,  40),  # Sapling
    7:  ( 20,  20,  20),  # Bedrock
    8:  ( 64, 100, 200),  # Water (flowing)
    9:  ( 64, 100, 200),  # Water (still)
    10: (220, 100,  30),  # Lava (flowing)
    11: (220, 100,  30),  # Lava (still)
    12: (215, 200, 140),  # Sand
    13: (150, 130, 110),  # Gravel
    14: (200, 185,  60),  # Gold Ore
    15: (160, 120,  80),  # Iron Ore
    16: ( 80,  80,  80),  # Coal Ore
    17: (160, 115,  60),  # Log
    18: ( 60, 160,  60),  # Leaves
    19: (200, 200, 100),  # Sponge
    20: (190, 230, 240),  # Glass
    21: ( 30,  60, 160),  # Lapis Lazuli Ore
    22: ( 40,  80, 200),  # Lapis Lazuli Block
    24: (220, 195, 130),  # Sandstone
    25: (100,  70,  50),  # Note Block
    35: (220, 220, 220),  # Wool (White)
    37: (230, 220,  50),  # Dandelion
    38: (220,  60,  60),  # Rose
    39: (160, 110,  70),  # Brown Mushroom
    40: (200,  50,  50),  # Red Mushroom
    41: (235, 215,  60),  # Gold Block
    42: (210, 210, 210),  # Iron Block
    43: (170, 170, 170),  # Double Stone Slab
    44: (170, 170, 170),  # Stone Slab
    45: (170,  90,  70),  # Brick
    46: (200,  80,  40),  # TNT
    47: (140, 100,  60),  # Bookshelf
    48: (100, 130,  80),  # Mossy Cobblestone
    49: ( 30,  20,  50),  # Obsidian
    50: (255, 220,  50),  # Torch
    51: (255, 150,  20),  # Fire
    52: ( 60,  80, 100),  # Mob Spawner
    53: (180, 140,  80),  # Oak Stairs
    54: (160, 115,  60),  # Chest
    55: (180,  30,  30),  # Redstone Wire
    56: ( 80, 200, 200),  # Diamond Ore
    57: (100, 220, 220),  # Diamond Block
    58: (160, 115,  60),  # Crafting Table
    59: (130, 170,  50),  # Wheat
    60: (120,  80,  50),  # Farmland
    61: (130, 130, 130),  # Furnace
    62: (160, 100,  40),  # Lit Furnace
    63: (160, 115,  60),  # Standing Sign
    64: (140,  95,  55),  # Wood Door
    65: (150, 120,  70),  # Ladder
    66: (150, 140, 130),  # Rail
    67: (155, 155, 155),  # Cobblestone Stairs
    68: (160, 115,  60),  # Wall Sign
    69: (120, 100,  70),  # Lever
    70: (136, 136, 136),  # Stone Pressure Plate
    71: (200, 200, 200),  # Iron Door
    72: (180, 140,  80),  # Wood Pressure Plate
    73: (160,  60,  60),  # Redstone Ore
    74: (200,  80,  80),  # Lit Redstone Ore
    75: (100,  20,  20),  # Redstone Torch (off)
    76: (220,  60,  60),  # Redstone Torch (on)
    77: (136, 136, 136),  # Stone Button
    78: (240, 245, 250),  # Snow Layer
    79: (180, 220, 240),  # Ice
    80: (240, 245, 250),  # Snow Block
    81: ( 50, 130,  50),  # Cactus
    82: (170, 175, 185),  # Clay
    83: (130, 180,  80),  # Sugar Cane
    84: (140,  90,  60),  # Jukebox
    85: (140, 110,  60),  # Fence
    86: (200, 130,  30),  # Pumpkin
    87: (165,  95,  65),  # Netherrack
    88: ( 80,  70,  60),  # Soul Sand
    89: (240, 215, 100),  # Glowstone
    90: (120,  60, 180),  # Nether Portal
    91: (200, 130,  20),  # Jack-o-Lantern
    92: (240, 180, 180),  # Cake
    93: (136, 136, 136),  # Redstone Repeater (off)
    94: (180, 100, 100),  # Redstone Repeater (on)
}
DEFAULT_COLOUR = (180, 80, 180)   # Magenta = unknown block ID
AIR_ID = 0

BLOCK_NAMES = {
    1:  "Stone",           2:  "Grass",           3:  "Dirt",
    4:  "Cobblestone",     5:  "Wood Planks",      6:  "Sapling",
    7:  "Bedrock",         8:  "Water",            9:  "Water (still)",
    10: "Lava",           11:  "Lava (still)",    12:  "Sand",
    13: "Gravel",         14:  "Gold Ore",        15:  "Iron Ore",
    16: "Coal Ore",       17:  "Log",             18:  "Leaves",
    19: "Sponge",         20:  "Glass",           21:  "Lapis Lazuli Ore",
    22: "Lapis Block",    24:  "Sandstone",       25:  "Note Block",
    35: "Wool",           37:  "Dandelion",       38:  "Rose",
    39: "Brown Mushroom", 40:  "Red Mushroom",    41:  "Gold Block",
    42: "Iron Block",     43:  "Double Slab",     44:  "Stone Slab",
    45: "Brick",          46:  "TNT",             47:  "Bookshelf",
    48: "Mossy Cobble",   49:  "Obsidian",        50:  "Torch",
    51: "Fire",           52:  "Mob Spawner",     53:  "Oak Stairs",
    54: "Chest",          55:  "Redstone Wire",   56:  "Diamond Ore",
    57: "Diamond Block",  58:  "Crafting Table",  59:  "Wheat",
    60: "Farmland",       61:  "Furnace",         62:  "Lit Furnace",
    63: "Sign",           64:  "Wood Door",       65:  "Ladder",
    66: "Rail",           67:  "Cobble Stairs",   68:  "Wall Sign",
    69: "Lever",          70:  "Stone Plate",     71:  "Iron Door",
    72: "Wood Plate",     73:  "Redstone Ore",    74:  "Lit Redstone Ore",
    75: "Redstone Torch", 76:  "Redstone Torch",  77:  "Stone Button",
    78: "Snow Layer",     79:  "Ice",             80:  "Snow Block",
    81: "Cactus",         82:  "Clay",            83:  "Sugar Cane",
    84: "Jukebox",        85:  "Fence",           86:  "Pumpkin",
    87: "Netherrack",     88:  "Soul Sand",       89:  "Glowstone",
    90: "Nether Portal",  91:  "Jack-o-Lantern",  92:  "Cake",
    93: "Repeater (off)", 94:  "Repeater (on)",
}

VALID_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def prompt(message: str) -> str:
    """Prompt for input, stripping surrounding quotes the user may paste in."""
    return input(message).strip().strip('"').strip("'")


def read_nbt_file(path: Path):
    """Load an NBT file. nbtlib.load() handles gzip automatically."""
    try:
        return nbtlib.load(str(path))
    except Exception:
        pass
    try:
        return nbtlib.File.parse(io.BytesIO(path.read_bytes()))
    except Exception:
        pass
    return None


def iter_chunks(world_path: Path):
    """Yield (cx, cz, nbt_data) for every chunk file in the world."""
    for sub1 in world_path.iterdir():
        if not sub1.is_dir():
            continue
        for sub2 in sub1.iterdir():
            if not sub2.is_dir():
                continue
            for chunk_file in sub2.iterdir():
                m = CHUNK_FILENAME_RE.match(chunk_file.name)
                if not m:
                    continue
                try:
                    cx = int(m.group(1), 36)
                    cz = int(m.group(2), 36)
                except ValueError:
                    continue
                nbt = read_nbt_file(chunk_file)
                if nbt is None:
                    continue
                yield cx, cz, nbt


def extract_level(nbt):
    """Extract the Level compound from a chunk NBT."""
    try:
        if "Level" in nbt:
            return nbt["Level"]
        root = nbt.get("") if hasattr(nbt, "get") else list(nbt.values())[0]
        return root["Level"]
    except Exception:
        return None


def get_surface(blocks_bytes: bytes):
    """
    Return two 16x16 grids: top block ID and top block Y for each (x, z).
    Alpha/Infdev XZY ordering: index = x*16*128 + z*128 + y
    """
    ids    = [[0]  * 16 for _ in range(16)]
    heights= [[64] * 16 for _ in range(16)]
    for x in range(16):
        for z in range(16):
            for y in range(127, -1, -1):
                idx = x * 16 * 128 + z * 128 + y
                if idx < len(blocks_bytes):
                    bid = blocks_bytes[idx]
                    if bid != AIR_ID:
                        ids[x][z]     = bid
                        heights[x][z] = y
                        break
    return ids, heights


def height_shade(colour: tuple, dy: int) -> tuple:
    """
    Shade a colour using directional (north-facing) shading, exactly like
    Minecraft's in-game map renderer.
    dy = this block's Y minus the Y of the block to its north:
      dy > 0  = going uphill   -> lighter
      dy == 0 = flat           -> normal
      dy < 0  = going downhill -> darker
    """
    if dy > 0:
        factor = 1.22   # lighter (Minecraft uses ~222/180 ratio)
    elif dy < 0:
        factor = 0.78   # darker  (Minecraft uses ~135/180 ratio)
    else:
        factor = 1.0    # flat = normal brightness
    return tuple(min(255, max(0, int(c * factor))) for c in colour)

# ---------------------------------------------------------------------------
# Level.dat reader
# ---------------------------------------------------------------------------

def read_level_dat(world_path: Path):
    level_dat = world_path / "level.dat"
    if not level_dat.exists():
        return None
    nbt = read_nbt_file(level_dat)
    if nbt is None:
        return None
    return nbt.get("Data") or nbt


def print_world_info(world_path: Path):
    data = read_level_dat(world_path)
    print("\n=== World Info ===")
    if data is None:
        print("  (could not read level.dat)")
        return
    try:
        print(f"  Seed        : {int(data['RandomSeed'])}")
    except Exception:
        pass
    try:
        px = float(data["Player"]["Pos"][0])
        py = float(data["Player"]["Pos"][1])
        pz = float(data["Player"]["Pos"][2])
        print(f"  Player pos  : X={px:.1f}  Y={py:.1f}  Z={pz:.1f}")
    except Exception:
        pass
    try:
        t = int(data["Time"])
        print(f"  World time  : {t} ticks  (~day {t // 24000})")
    except Exception:
        pass
    print()

# ---------------------------------------------------------------------------
# Chunk data loader (shared by both renderers)
# ---------------------------------------------------------------------------

def load_chunk_data(world_path: Path):
    """
    Scan all chunks and return a dict:
      (cx, cz) -> { "ids": 16x16, "heights": 16x16 }
    """
    print("Scanning chunks...")
    chunk_data = {}
    total = 0

    for cx, cz, nbt in iter_chunks(world_path):
        level = extract_level(nbt)
        if level is None:
            continue
        try:
            blocks_raw = bytes(level["Blocks"])
        except (KeyError, TypeError):
            continue

        ids, heights = get_surface(blocks_raw)

        try:
            cx = int(level["xPos"])
            cz = int(level["zPos"])
        except Exception:
            pass

        chunk_data[(cx, cz)] = {"ids": ids, "heights": heights}
        total += 1
        if total % 200 == 0:
            print(f"  ...{total} chunks loaded")

    print(f"  Loaded {total} chunks total.")
    return chunk_data

# ---------------------------------------------------------------------------
# Image builder (shared base)
# ---------------------------------------------------------------------------

def build_images(chunk_data: dict, ppb: int, heightmap: bool):
    """
    Build and return (img_clean, img_grid) PIL images.
    heightmap=True applies Minecraft-style directional (north-face) shading.
    """
    min_cx = min(k[0] for k in chunk_data)
    max_cx = max(k[0] for k in chunk_data)
    min_cz = min(k[1] for k in chunk_data)
    max_cz = max(k[1] for k in chunk_data)

    width_chunks  = max_cx - min_cx + 1
    height_chunks = max_cz - min_cz + 1
    img_w = width_chunks  * 16 * ppb
    img_h = height_chunks * 16 * ppb

    print(f"  Chunk range : X {min_cx}..{max_cx},  Z {min_cz}..{max_cz}")
    print(f"  Image size  : {img_w} x {img_h} px")
    print("  Rendering...")

    img = Image.new("RGB", (img_w, img_h), color=(30, 30, 30))
    pix = img.load()

    for (cx, cz), data in chunk_data.items():
        off_x = (cx - min_cx) * 16 * ppb
        off_z = (cz - min_cz) * 16 * ppb
        for x in range(16):
            for z in range(16):
                bid    = data["ids"][x][z]
                y      = data["heights"][x][z]
                colour = BLOCK_COLOURS.get(bid, DEFAULT_COLOUR)
                if heightmap:
                    # Get the Y of the block to the north (z-1)
                    if z > 0:
                        north_y = data["heights"][x][z - 1]
                    else:
                        # North block is in the chunk to the north (cz-1)
                        north_chunk = chunk_data.get((cx, cz - 1))
                        north_y = north_chunk["heights"][x][15] if north_chunk else y
                    colour = height_shade(colour, y - north_y)
                for dx in range(ppb):
                    for dz in range(ppb):
                        pix[off_x + x * ppb + dx, off_z + z * ppb + dz] = colour

    # Clean version saved before drawing grid
    img_clean = img.copy()

    # Draw grid + labels
    draw = ImageDraw.Draw(img)
    for i in range(width_chunks + 1):
        x = i * 16 * ppb
        draw.line([(x, 0), (x, img_h - 1)], fill=(0, 0, 0))
    for i in range(height_chunks + 1):
        z = i * 16 * ppb
        draw.line([(0, z), (img_w - 1, z)], fill=(0, 0, 0))

    if ppb >= 2:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        for cx_i in range(0, width_chunks, 4):
            for cz_i in range(0, height_chunks, 4):
                label = f"{min_cx + cx_i},{min_cz + cz_i}"
                draw.text(
                    (cx_i * 16 * ppb + 2, cz_i * 16 * ppb + 2),
                    label, fill=(255, 255, 255), font=font
                )

    return img_clean, img

# ---------------------------------------------------------------------------
# Output path prompt
# ---------------------------------------------------------------------------

def ask_output_path(label: str) -> Path:
    """Ask for a valid image output path, looping until one is provided."""
    while True:
        raw = prompt(f"Save {label} to (e.g. D:\\Pictures\\{label.replace(' ','_')}.png): ")
        p = Path(raw).resolve()
        ext = p.suffix.lower()
        if ext == "":
            print("  Oops! Looks like you forgot to add the filename.")
            print("  Make sure your path ends with something like \\infdev_map.png")
            print(f"  Supported formats: {', '.join(sorted(VALID_EXTENSIONS))}")
            continue
        if ext not in VALID_EXTENSIONS:
            print(f"  '{ext}' is not a supported image format.")
            print(f"  Supported formats: {', '.join(sorted(VALID_EXTENSIONS))}")
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

# ---------------------------------------------------------------------------
# Map render task
# ---------------------------------------------------------------------------

def task_render_map(world_path: Path, ppb: int):
    chunk_data = load_chunk_data(world_path)
    if not chunk_data:
        print("ERROR: No valid chunks found.")
        return

    print("\nWhich map versions would you like?")
    print("  1 = Flat only")
    print("  2 = Shaded map only")
    print("  3 = Both")
    choice = prompt("Choice (1/2/3): ").strip()

    do_flat   = choice in ("1", "3")
    do_height = choice in ("2", "3")

    # Ask once for a base path; all output variants are derived from it
    base_out = ask_output_path("map image")
    stem   = base_out.stem
    ext    = base_out.suffix
    parent = base_out.parent

    if do_flat:
        print("\n--- Flat map ---")
        flat_clean, flat_grid = build_images(chunk_data, ppb, heightmap=False)
        flat_clean_path = parent / f"{stem}_flat_clean{ext}"
        flat_grid_path  = parent / f"{stem}_flat{ext}"
        flat_clean.save(str(flat_clean_path))
        flat_grid.save(str(flat_grid_path))
        print(f"  Flat clean -> {flat_clean_path}")
        print(f"  Flat grid  -> {flat_grid_path}")

    if do_height:
        print("\n--- Shaded map ---")
        shaded_clean, shaded_grid = build_images(chunk_data, ppb, heightmap=True)
        shaded_clean_path = parent / f"{stem}_shaded_clean{ext}"
        shaded_grid_path  = parent / f"{stem}_shaded{ext}"
        shaded_clean.save(str(shaded_clean_path))
        shaded_grid.save(str(shaded_grid_path))
        print(f"  Shaded clean -> {shaded_clean_path}")
        print(f"  Shaded grid  -> {shaded_grid_path}")

# ---------------------------------------------------------------------------
# Block search task
# ---------------------------------------------------------------------------

def task_search_blocks(world_path: Path):
    print("\nBlock IDs for common blocks:")
    print("  1=Stone   2=Grass   7=Bedrock  12=Sand   14=Gold Ore")
    print("  15=Iron Ore  16=Coal Ore  21=Lapis Ore  49=Obsidian")
    print("  52=Mob Spawner  54=Chest  56=Diamond Ore  73=Redstone Ore")

    try:
        target_id = int(prompt("Enter block ID to search for: "))
    except ValueError:
        print("  Invalid block ID.")
        return

    name = BLOCK_NAMES.get(target_id, f"Block ID {target_id}")
    print(f"\nSearching for {name} (ID {target_id}) across all chunks...")
    found = []

    for cx, cz, nbt in iter_chunks(world_path):
        level = extract_level(nbt)
        if level is None:
            continue
        try:
            blocks_raw = bytes(level["Blocks"])
            real_cx = int(level["xPos"])
            real_cz = int(level["zPos"])
        except Exception:
            continue

        for i, bid in enumerate(blocks_raw):
            if bid == target_id:
                y = i % 128
                z = (i // 128) % 16
                x = (i // 128) // 16
                found.append((real_cx * 16 + x, y, real_cz * 16 + z))

    if not found:
        print(f"  No {name} found in any chunk.")
    else:
        print(f"  Found {len(found)} block(s). First 30 locations (X, Y, Z):")
        for wx, wy, wz in found[:30]:
            print(f"    X={wx:6d}  Y={wy:3d}  Z={wz:6d}")
        if len(found) > 30:
            remaining = len(found) - 30
            print(f"    ... and {remaining} more.")
            do_export = prompt(f"  Export all {len(found)} coordinates to a .txt file? (y/n): ").lower()
            if do_export == "y":
                while True:
                    export_path = Path(prompt("  Save txt to (e.g. D:\\Pictures\\diamond_ore.txt): ")).resolve()
                    if export_path.suffix.lower() != ".txt":
                        print("  Please use a .txt extension.")
                        continue
                    export_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with open(export_path, "w") as f:
                            f.write(f"Block: {name} (ID {target_id})\n")
                            f.write(f"Total found: {len(found)}\n")
                            f.write("-" * 35 + "\n")
                            for wx, wy, wz in found:
                                f.write(f"X={wx:6d}  Y={wy:3d}  Z={wz:6d}\n")
                        print(f"  Exported -> {export_path}")
                    except Exception as e:
                        print(f"  Export failed: {e}")
                    break
                
# ---------------------------------------------------------------------------
# Edit chunks task
# ---------------------------------------------------------------------------

#start up the actual window and render the image
def task_edit_chunks(world_path: Path):
    from PIL import ImageTk
    chunk_data = load_chunk_data(world_path)
    if not chunk_data:
        print("ERROR: No valid chunks found.")
        return

#calculates what chunks are on screen
    def get_visible_chunks():
        nonlocal offset_x, offset_y, zoom_level, min_cx, min_cz
        start_cx = int(min_cx + ((0 - offset_x) / zoom_level) // 16)
        start_cz = int(min_cz + ((0 - offset_y) / zoom_level) // 16)
        end_cx = int(min_cx + ((canvas.winfo_width() - offset_x) / zoom_level) //16)
        end_cz = int(min_cz + ((canvas.winfo_height() - offset_y) / zoom_level) //16)
        return start_cx, start_cz, end_cx, end_cz

#uses the visible chunks and renders only the visible chunks to improve performance
    def render_visible_chunks():
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        start_cx, start_cz, end_cx, end_cz = get_visible_chunks()
        
        # Render at 1px per block
        chunk_w = (end_cx - start_cx + 1) * 16
        chunk_h = (end_cz - start_cz + 1) * 16
        img = Image.new("RGB", (chunk_w, chunk_h), color=(30, 30, 30))
        pix = img.load()
        
        for (cx, cz), data in chunk_data.items():
            if start_cx <= cx <= end_cx and start_cz <= cz <= end_cz:
                px = (cx - start_cx) * 16
                pz = (cz - start_cz) * 16
                for x in range(16):
                    for z in range(16):
                        bid = data["ids"][x][z]
                        colour = BLOCK_COLOURS.get(bid, DEFAULT_COLOUR)
                        pix[px + x, pz + z] = colour
        
        # Scale up using PIL - fast C code
        scaled_w = int(chunk_w * zoom_level)
        scaled_h = int(chunk_h * zoom_level)
        img = img.resize((max(1, scaled_w), max(1, scaled_h)), Image.NEAREST)
        
        # Paste onto canvas-sized image at correct offset
        result = Image.new("RGB", (w, h), color=(30, 30, 30))
        paste_x = int((start_cx - min_cx) * 16 * zoom_level + offset_x)  
        paste_y = int((start_cz - min_cz) * 16 * zoom_level + offset_y)
        result.paste(img, (paste_x, paste_y))
        return result
        
    
    root = tk.Tk()
    root.title("Infdev Chunk Editor")
    root.geometry("800x600")
    canvas = tk.Canvas(root, bg="black")
    canvas.pack(fill=tk.BOTH, expand=True)
    min_cx = min(k[0] for k in chunk_data)
    min_cz = min(k[1] for k in chunk_data)
    offset_x = 0
    offset_y = 0
    zoom_level = 1.0
    root.update()
    tk_image = ImageTk.PhotoImage(render_visible_chunks())
    image_id = canvas.create_image(0, 0, anchor=tk.NW, image=tk_image)

#highlight selected chunks left mouse button
    selected_chunks = {}
    def select_chunks(event):
        nonlocal offset_x, offset_y
        chunk_x = min_cx + ((event.x - offset_x) / zoom_level) // 16
        chunk_z = min_cz + ((event.y - offset_y) / zoom_level) // 16
        print(chunk_x, chunk_z)
        if (chunk_x, chunk_z) in selected_chunks:
            canvas.delete(selected_chunks[(chunk_x, chunk_z)])
            del selected_chunks[(chunk_x, chunk_z)]
        else:
            rect_id = canvas.create_rectangle(
                (chunk_x - min_cx) * 16 * zoom_level + offset_x,
                (chunk_z - min_cz) * 16 * zoom_level + offset_y,
                (chunk_x - min_cx + 1) * 16 * zoom_level + offset_x,
                (chunk_z - min_cz + 1) * 16 * zoom_level + offset_y,
                outline="magenta",
                width=2
            )
            selected_chunks[(chunk_x, chunk_z)] = rect_id
    canvas.bind("<Button-1>", select_chunks)

#click right mouse button and drag mouse to move
    drag_start_x = 1
    drag_start_y = 1
    def on_drag(event):
        nonlocal drag_start_x, drag_start_y
        drag_start_x = event.x
        drag_start_y = event.y
    canvas.bind("<ButtonPress-3>", on_drag)

    def on_drag_move(event):
        nonlocal offset_x, offset_y
        nonlocal drag_start_x, drag_start_y
        nonlocal tk_image
        dx = event.x - drag_start_x
        dy = event.y - drag_start_y
        offset_x += dx
        offset_y += dy
        rendered = render_visible_chunks()
        tk_image = ImageTk.PhotoImage(rendered)
        canvas.itemconfig(image_id, image=tk_image)
        drag_start_x = event.x
        drag_start_y = event.y
        for (cx, cz), rect_id in selected_chunks.items():
            canvas.delete(rect_id)
        for (cx, cz) in list(selected_chunks.keys()):
            rect_id = canvas.create_rectangle(
                (cx - min_cx) * 16 * zoom_level + offset_x,
                (cz - min_cz) * 16 * zoom_level + offset_y,
                (cx - min_cx + 1) * 16 * zoom_level + offset_x,
                (cz - min_cz + 1) * 16 * zoom_level + offset_y,
                outline="magenta",
                width=2
            )
            selected_chunks[(cx, cz)] = rect_id

    def on_drag_release(event):
        pass

#zoom in and out of the map with scroll wheel
    def on_zoom(event):
        nonlocal zoom_level, tk_image, offset_x, offset_y
        old_zoom = zoom_level
        if event.delta > 0:
            zoom_level *= 1.1
        else:
            zoom_level *= 0.9
        zoom_level = max(0.01, min(30.0, zoom_level))
        cx_screen = canvas.winfo_width() / 2
        cy_screen = canvas.winfo_height() / 2
        offset_x = cx_screen - (cx_screen - offset_x) * (zoom_level / old_zoom)
        offset_y = cy_screen - (cy_screen - offset_y) * (zoom_level / old_zoom)
        print(offset_x, offset_y)
        rendered = render_visible_chunks()
        tk_image = ImageTk.PhotoImage(rendered)
        canvas.itemconfig(image_id, image=tk_image)
        for (cx, cz), rect_id in selected_chunks.items():
            canvas.delete(rect_id)
        for (cx, cz) in list(selected_chunks.keys()):
            rect_id = canvas.create_rectangle(
                (cx - min_cx) * 16 * zoom_level + offset_x,
                (cz - min_cz) * 16 * zoom_level + offset_y,
                (cx - min_cx + 1) * 16 * zoom_level + offset_x,
                (cz - min_cz + 1) * 16 * zoom_level + offset_y,
                outline="magenta",
                width=2
            )
            selected_chunks[(cx, cz)] = rect_id

    root.bind("<MouseWheel>", on_zoom)
    canvas.bind("<B3-Motion>", on_drag_move)
    canvas.bind("<ButtonRelease-3>", on_drag_release)
    root.update()
    test = render_visible_chunks()
    print(test.size)
    root.mainloop()
    
# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Infdev/Alpha Minecraft world map viewer & block finder"
    )
    parser.add_argument("world",
        help="Path to world folder (contains level.dat)")
    parser.add_argument("--scale", "-s", type=int, default=2,
        help="Pixels per block (default: 2). Use 1 for large worlds, 4 for detail.")
    parser.add_argument("--info", "-i", action="store_true",
        help="Print world info only and exit.")

    args = parser.parse_args()
    world_path = Path(args.world).expanduser().resolve()

    if not world_path.is_dir():
        print(f"ERROR: '{world_path}' is not a directory.")
        sys.exit(1)
    if not (world_path / "level.dat").exists():
        print(f"ERROR: No level.dat found in '{world_path}'.")
        sys.exit(1)

    print_world_info(world_path)

    if args.info:
        sys.exit(0)

    # --- Main menu loop ---
    while True:
        print("=" * 40)
        print("  What would you like to do?")
        print("  1 = Render map image(s)")
        print("  2 = Search for blocks")
        print("  3 = Edit Chunks")
        print("  4 = Quit")
        print("=" * 40)
        choice = prompt("Choice (1/2/3/4): ").strip()

        if choice == "1":
            task_render_map(world_path, args.scale)
        elif choice == "2":
            task_search_blocks(world_path)
        elif choice == "3":
            task_edit_chunks(world_path)
        elif choice == "4":
            print("\nDone!")
            break
        else:
            print("  Please enter 1, 2, 3, or 4.")


if __name__ == "__main__":
    main()
