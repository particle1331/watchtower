function Para(el)
  if quarto.doc.isFormat('pdf') then
    local has_image = false
    for _, item in ipairs(el.content) do
      if item.t == 'Image' then
        has_image = true
        break
      end
    end
    if has_image then
      return {
        pandoc.RawBlock('latex', '\\begin{center}'),
        el,
        pandoc.RawBlock('latex', '\\end{center}')
      }
    end
  end
end