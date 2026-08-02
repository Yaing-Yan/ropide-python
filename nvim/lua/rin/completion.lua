-- 补全源注册分发：按用户安装的补全插件注册（blink.cmp / nvim-cmp）

local M = {}

function M.setup()
  if vim.g.rin_completion_registered then
    return
  end
  vim.g.rin_completion_registered = true

  local ok_blink = pcall(require, 'rin.blink')
  if ok_blink then
    require('rin.blink').setup()
  end

  local ok_cmp = pcall(require, 'rin.cmp')
  if ok_cmp then
    require('rin.cmp').setup()
  end
end

return M
