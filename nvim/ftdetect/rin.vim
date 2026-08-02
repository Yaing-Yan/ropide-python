" Vim filetype detection for RopIDE .rin files
" Loads gadgets.json from the .rin project directory for gadget validation
" and completion (see autoload/rin.vim).

au BufRead,BufNewFile *.rin setfiletype rin
