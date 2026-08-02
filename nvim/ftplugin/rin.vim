" Vim filetype plugin for RopIDE .rin scripts

setlocal omnifunc=rin#gadgets#omnifunc
setlocal commentstring=//\ %s

" 注册补全源（blink.cmp / nvim-cmp，均未安装时自动跳过，仍可用 <C-x><C-o>）
lua require('rin.completion').setup()

" Reload gadgets.json (and gadget-based highlighting) after editing it.
if !exists('b:rin_reload_cmd')
  command! -buffer RinReload
        \ call rin#gadgets#clear() |
        \ syntax clear |
        \ unlet! b:current_syntax |
        \ runtime! syntax/rin.vim
  let b:rin_reload_cmd = 1
endif
