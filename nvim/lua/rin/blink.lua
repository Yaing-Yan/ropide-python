-- blink.cmp source for RopIDE .rin gadgets
-- 与 Python 补全同样的自动弹出体验：输入 '#' 后自动弹出候选，
-- 数据来自 rin#gadgets#list()（.rin 项目目录的 gadgets.json）。
-- 前缀 '-'（#-po）自动生成禁止 00 字节的 #-name; 形式。

local M = {}

function M.new(opts)
  local self = setmetatable({}, { __index = M })
  self.opts = opts or {}
  return self
end

function M:enabled()
  return vim.bo.filetype == 'rin'
end

function M:get_trigger_characters()
  return { '#' }
end

-- 返回 "#name" 在行内的 1 基起始位置；光标后无 "#" 返回 nil
local function keyword_start(line, cursor_col)
  local prefix = line:sub(1, cursor_col - 1)
  local ci = prefix:find('//', 1, true)
  if ci then
    prefix = prefix:sub(1, ci - 1)
  end
  return prefix:match('()#[%w%-]*$')
end

function M:get_completions(ctx, callback)
  local cur_line, cur_col = unpack(ctx.cursor)
  local start = keyword_start(ctx.line, cur_col)
  if not start then
    callback({ items = {} })
    return
  end
  local word = ctx.line:sub(start, cur_col - 1)
  local allow00 = word:sub(2, 2) ~= '-'
  local items = {}
  for _, g in ipairs(vim.fn['rin#gadgets#list']()) do
    local name = g.name or ''
    if name ~= '' then
      local insert = '#' .. (allow00 and '' or '-') .. name .. ';'
      table.insert(items, {
        label = insert,
        kind = vim.lsp.protocol.CompletionItemKind.Function,
        detail = '0x' .. (g.addr or ''),
        documentation = {
          kind = 'markdown',
          value = (g.desc or ''):match('[^\n]*'),
        },
        textEdit = {
          newText = insert,
          range = {
            start = { line = cur_line - 1, character = start - 1 },
            ['end'] = { line = cur_line - 1, character = cur_col },
          },
        },
      })
    end
  end
  callback({ items = items, is_incomplete_backward = true, is_incomplete_forward = true })
end

function M.setup()
  if vim.g.rin_blink_registered then
    return
  end
  vim.g.rin_blink_registered = true
  local ok, blink = pcall(require, 'blink.cmp')
  if not ok then
    return
  end
  -- 注册 provider（已存在时忽略）并自动启用到 rin 文件类型
  pcall(blink.add_source_provider, 'rin', {
    name = 'rin',
    module = 'rin.blink',
    max_items = 50,
  })
  pcall(blink.add_filetype_source, 'rin', 'rin')
end

return M
