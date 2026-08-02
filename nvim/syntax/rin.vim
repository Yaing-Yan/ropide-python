" Vim syntax file for RopIDE .rin scripts (fx-991CNX ROP)
" Highlight format follows rop-ide (https://ropide.pages.dev) — see
" /home/yanshangxuan/rop-ide/src/parser.js and styles/InputPanel.module.scss.
"
" Groups (named after the web IDE classes):
"   comment          // comment                    #888, italic
"   constant         $name = value;                name #0b7285 / value #5c940d
"   constantWarning  malformed constant            name color + wavy underline
"   gadget           #name;  (known: bg #e7f5ff)   #1864ab
"   gadgetWarning    #unknown;                     + wavy underline
"   value            [expr]  (closed: bg #fff9db)  #e67700
"   valueWarning     [bad expr]                    + wavy underline
"   anchor           <name> (closed: bg #e6fcf5)   #087f5b
"   hex              00 11 AA                      default fg (black on light bg)
"
" Unknown closed gadgets get the warning style, same as the web IDE
" (gadgets not present in the project's gadgets.json).
"
" Note: when several patterns match at the same position the LAST defined
" one wins, so generic patterns come first and specific ones last.

if exists('b:current_syntax')
  finish
endif

" gadget names from the .rin project's gadgets.json (empty if none/unreadable)
let s:rin_gadget_names = rin#gadgets#names()

" comment //...
syn match rinComment '//.*' contains=@Spell

" constant $name = value; (order: name-only < warning < valid)
syn match rinConstant '\$[A-Za-z0-9_]*' contains=rinConstantName
syn match rinConstantWarning '\$[A-Za-z0-9_]*[^;]*;'
syn match rinConstant '\$[A-Za-z0-9_]*\s*=\s*-\?\(0x\)\?[0-9a-fA-F]\+;'
      \ contains=rinConstantName,rinConstantEqual,rinConstantValue
syn match rinConstantName '\$[A-Za-z0-9_]*' contained
syn match rinConstantEqual '=' contained
syn match rinConstantValue '-\?\(0x\)\?[0-9a-fA-F]\+' contained

" gadget #name; / #-name; (order: plain < generic warning < known names)
syn match rinGadget '\#[^ ;\n]*'
syn match rinGadgetWarning '\#[^ ;\n]*;'
if !empty(s:rin_gadget_names)
  for rin_g in s:rin_gadget_names
    exe 'syn match rinGadgetClosed "#' . escape(rin_g, '~"\[\]\\.^$*') . ';"'
    exe 'syn match rinGadgetClosed "#-' . escape(rin_g, '~"\[\]\\.^$*') . ';"'
  endfor
  unlet rin_g
endif

" value [expr] (order: plain < closed < warning)
syn match rinValue '\[[^\]]*'
syn match rinValueClosed '\[[^\]]*\]'
syn match rinValueWarning '\[[0-9a-fA-F$ \t+-]*\(\$[A-Za-z0-9_]*\)\@<![^\]0-9a-fA-F$ \t+-][^\]]*\]'

" anchor <name> / <-name> (order: plain < closed)
syn match rinAnchor '<[^ >]*'
syn match rinAnchorClosed '<[^ >]*>'

" raw hex bytes
syn match rinHex '[0-9a-fA-F]\+'

" highlights — colors follow rop-ide InputPanel.module.scss
if &background ==# 'light'
  hi def rinHex guifg=#000000 gui=bold
  hi def rinComment guifg=#888888 ctermfg=8 gui=italic cterm=italic
  hi def rinConstantName guifg=#0b7285 ctermfg=6
  hi def rinConstantEqual guifg=#343a40 ctermfg=8
  hi def rinConstantValue guifg=#5c940d ctermfg=2
  hi def rinConstantWarning guifg=#0b7285 ctermfg=6
        \ gui=undercurl guisp=#d29200 cterm=underline term=underline
  hi def rinGadgetClosed guifg=#1864ab ctermfg=4 guibg=#e7f5ff ctermbg=14
        \ gui=underline cterm=underline
  hi def rinGadgetWarning guifg=#1864ab ctermfg=4
        \ gui=undercurl guisp=#d29200 cterm=underline term=underline
  hi def rinGadget guifg=#1864ab ctermfg=4
  hi def rinValueClosed guifg=#e67700 ctermfg=3 guibg=#fff9db ctermbg=11
  hi def rinValueWarning guifg=#e67700 ctermfg=3
        \ gui=undercurl guisp=#d29200 cterm=underline term=underline
  hi def rinValue guifg=#e67700 ctermfg=3
  hi def rinAnchorClosed guifg=#087f5b ctermfg=2 guibg=#e6fcf5 ctermbg=10
  hi def rinAnchor guifg=#087f5b ctermfg=2
else
  " dark: 有效块用接近黑色的深色底、亮色前景
  hi def link rinHex Normal
  hi def rinComment guifg=#858585 ctermfg=8 gui=italic cterm=italic
  hi def rinConstantName guifg=#22b8cf ctermfg=14
  hi def rinConstantEqual guifg=#868e96 ctermfg=8
  hi def rinConstantValue guifg=#82c91e ctermfg=10
  hi def rinConstantWarning guifg=#22b8cf ctermfg=14
        \ gui=undercurl guisp=#ffc078 cterm=underline term=underline
  hi def rinGadgetClosed guifg=#4dabf7 ctermfg=12 guibg=#101f33
        \ gui=underline cterm=underline
  hi def rinGadgetWarning guifg=#4dabf7 ctermfg=12
        \ gui=undercurl guisp=#ffc078 cterm=underline term=underline
  hi def rinGadget guifg=#4dabf7 ctermfg=12
  hi def rinValueClosed guifg=#ffa94d ctermfg=11 guibg=#211a10
  hi def rinValueWarning guifg=#ffa94d ctermfg=11
        \ gui=undercurl guisp=#ffc078 cterm=underline term=underline
  hi def rinValue guifg=#ffa94d ctermfg=11
  hi def rinAnchorClosed guifg=#63e6be ctermfg=10 guibg=#10241d
  hi def rinAnchor guifg=#63e6be ctermfg=10
endif
hi def rinOther guifg=#777777 ctermfg=8

let b:current_syntax = 'rin'
