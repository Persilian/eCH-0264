-- Quarto filter for docs/de (registered in docs/de/_metadata.yml): shows a modelling
-- decision next to an excerpt of the data model.
--
--   ::: {.entscheid}
--   Text of the decision ...
--
--   ![](assets/excerpts/name.svg){fig-alt="Description of the excerpt"}
--   :::
--
-- The last block with an image is the excerpt, everything before it is the
-- text. Narrow excerpts stand next to the text, wide ones below it, so that
-- their labels stay readable; the width is read from the SVG file.
--
--   * HTML: CSS grid (entscheid.css, added as HTML dependency), stacked on
--     narrow screens;
--   * Typst (PDF): #grid with two columns;
--   * other formats (Markdown, Word): the text followed by the excerpt.

-- Widest excerpt (in SVG pixels) that is placed next to the text.
local MAX_SIDE_BY_SIDE = 440
-- Width of the text in the PDF (A4 minus 2 cm and 1.5 cm margin) and the
-- largest share the excerpt may take next to the text.
local PDF_TEXT_WIDTH_PT = 496
local PDF_MAX_FIGURE_PT = 235

-- Width of an SVG file in pixels (PlantUML writes "width:123px" into the
-- style of the root element), or nil.
local function svg_width(src)
  local path = pandoc.path.join({ pandoc.path.directory(quarto.doc.input_file), src })
  local file = io.open(path, "r")
  if not file then return nil end
  local head = file:read(2000) or ""
  file:close()
  local width = head:match("width:(%d+)px") or head:match('width="(%d+)')
  return width and tonumber(width) or nil
end

-- Sets an attribute on the images of the blocks (walk returns a copy).
local function with_image_attribute(blocks, key, value)
  return blocks:walk({ Image = function(img) img.attributes[key] = value; return img end })
end

local function find_image(block)
  local image
  block:walk({ Image = function(img) image = img end })
  return image
end

function Div(div)
  if not div.classes:includes("entscheid") then return nil end

  -- Split into text and excerpt at the last block containing an image.
  local split, image
  for i = #div.content, 1, -1 do
    image = find_image(div.content[i])
    if image then split = i; break end
  end
  if not split then return nil end
  local text, figure = pandoc.Blocks({}), pandoc.Blocks({})
  for i, block in ipairs(div.content) do
    (i < split and text or figure):insert(block)
  end

  local px = svg_width(image.src)
  local side_by_side = px ~= nil and px <= MAX_SIDE_BY_SIDE

  if quarto.doc.is_format("html") then
    quarto.doc.add_html_dependency({
      name = "entscheid", version = "1.0", stylesheets = { "entscheid.css" },
    })
    if px then figure = with_image_attribute(figure, "style", string.format("width: %dpx;", px)) end
    local classes = { "entscheid", side_by_side and "entscheid-nebeneinander" or "entscheid-untereinander" }
    return pandoc.Div({
      pandoc.Div(text, pandoc.Attr("", { "entscheid-text" })),
      pandoc.Div(figure, pandoc.Attr("", { "entscheid-abbildung" })),
    }, pandoc.Attr(div.identifier, classes))
  end

  if quarto.doc.is_format("typst") then
    if px then
      local limit = side_by_side and PDF_MAX_FIGURE_PT or PDF_TEXT_WIDTH_PT
      figure = with_image_attribute(figure, "width", string.format("%.0fpt", math.min(px * 0.75, limit)))
    end
    if not side_by_side then
      text:extend(figure)
      return text
    end
    local blocks = pandoc.Blocks({
      pandoc.RawBlock("typst", "#grid(columns: (1fr, auto), column-gutter: 1.5em, align: top, ["),
    })
    blocks:extend(text)
    blocks:insert(pandoc.RawBlock("typst", "], ["))
    blocks:extend(figure)
    blocks:insert(pandoc.RawBlock("typst", "])"))
    return blocks
  end

  text:extend(figure)
  return text
end
