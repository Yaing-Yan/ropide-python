-- nvim-cmp source for RopIDE .rin gadgets（blink.cmp 用户请使用 rin.blink）
-- 输入 '#' 后自动弹出候选，数据来自 rin#gadgets#list()。

local M = {}

local source = {}

source.new = function()
  return setmetatable({}, { __index = source })
end

function source:get_debug_name()
  return 'rin'
end

function source:is_available()
  return vim.bo.filetype == 'rin'
end

function source:get_trigger_characters()
  return { '#' }
end

function source:get_keyword_pattern()
  return '#[%w%-]*'
end

function source:complete(params, callback)
  local before = params.context.cursor_before_line
  local ci = before:find('//', 1, true)
  if ci then
    before = before:sub(1, ci - 1)
  end
  local dash, query = before:match('#(-?)([a-zA-Z0-9-]*)$')
  if not dash then
    callback({})
    return
  end
  local allow00 = dash ~= '-'
  local ok, cmp = pcall(require, 'cmp')
  if not ok then
    callback({})
    return
  end
  local items = {}
  for _, g in ipairs(vim.fn['rin#gadgets#list']()) do
    local name = g.name or ''
    if name:lower():find(query:lower(), 1, true) then
      local insert = '#' .. (allow00 and '' or '-') .. name .. ';'
      table.insert(items, {
        label = insert,
        insertText = insert,
        kind = cmp.lsp.CompletionItemKind.Function,
        detail = '0x' .. (g.addr or ''),
        documentation = (g.desc or ''):match('[^\n]*'),
        menu = 'gadget',
      })
    end
  end
  callback(items)
end

function M.setup()
  local ok, cmp = pcall(require, 'cmp')
  if ok then
    cmp.register_source('rin', source.new())
  end
end

return M
