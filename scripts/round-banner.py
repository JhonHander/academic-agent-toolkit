from PIL import Image, ImageDraw

input_path = "public/banner.png"
output_path = "public/banner-rounded.png"
radius = 30
scale = 8  # supersampling factor for antialiasing

img = Image.open(input_path).convert("RGBA")
w, h = img.size

mask = Image.new("L", (w * scale, h * scale), 0)
draw = ImageDraw.Draw(mask)
draw.rounded_rectangle(
    (0, 0, w * scale, h * scale), radius=radius * scale, fill=255
)
mask = mask.resize(img.size, Image.LANCZOS)

rounded = Image.new("RGBA", img.size, (255, 255, 255, 0))
rounded.paste(img, (0, 0), mask)

rounded.save(output_path)
print(f"Saved {output_path}")
