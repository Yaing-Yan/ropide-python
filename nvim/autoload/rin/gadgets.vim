" autoload/rin/gadgets.vim — RopIDE .rin gadget support
" Gadget data comes from the gadgets.json next to the current .rin file
" (the project folder created by ropide-python), searched upwards.

" Find gadgets.json starting from the current buffer's directory.
function! rin#gadgets#find_file() abort
  let l:dir = expand('%:p:h')
  while l:dir !=# '' && l:dir !=# '/'
    let l:json = l:dir . '/gadgets.json'
    if filereadable(l:json)
      return l:json
    endif
    let l:parent = fnamemodify(l:dir, ':h')
    if l:parent ==# l:dir
      break
    endif
    let l:dir = l:parent
  endwhile
  return ''
endfunction

" Parse and cache the gadget list (cache is buffer-local).
function! rin#gadgets#list() abort
  let l:path = rin#gadgets#find_file()
  if exists('b:rin_gadgets') && get(b:, 'rin_gadgets_path', '') ==# l:path
    return b:rin_gadgets
  endif
  let l:list = []
  if l:path !=# ''
    try
      let l:list = json_decode(join(readfile(l:path, 'b'), ''))
      if type(l:list) !=# v:t_list
        let l:list = []
      endif
    catch
      let l:list = []
    endtry
  endif
  let b:rin_gadgets = l:list
  let b:rin_gadgets_path = l:path
  return l:list
endfunction

" Gadget names only (used by syntax/rin.vim for validation).
function! rin#gadgets#names() abort
  let l:names = []
  for g in rin#gadgets#list()
    call add(l:names, get(l:g, 'name', ''))
  endfor
  return l:names
endfunction

" Drop the buffer-local cache (call before re-sourcing syntax).
function! rin#gadgets#clear() abort
  unlet! b:rin_gadgets b:rin_gadgets_path
endfunction

" Omni completion (<C-x><C-o>) for gadgets, mirroring the rop-ide web UI:
" trigger after '#', '-' prefix disables 00-byte gadget, insert '#name;'.
function! rin#gadgets#omnifunc(findstart, base) abort
  if a:findstart
    let l:line = getline('.')
    let l:col = col('.') - 1
    if l:col <= 0
      return -1
    endif
    let l:before = strpart(l:line, 0, l:col)
    let l:ci = stridx(l:before, '//')
    if l:ci >= 0
      let l:before = strpart(l:before, 0, l:ci)
    endif
    let l:m = matchstrpos(l:before, '#[a-zA-Z0-9-]*$')
    if l:m[1] < 0
      return -3
    endif
    return l:m[1]
  endif
  let l:raw = strpart(a:base, 1)
  let l:allow00 = l:raw[0] !=# '-'
  let l:q = l:allow00 ? l:raw : strpart(l:raw, 1)
  let l:items = []
  for g in rin#gadgets#list()
    if stridx(tolower(get(l:g, 'name', '')), tolower(l:q)) < 0
      continue
    endif
    let l:word = '#' . (l:allow00 ? '' : '-') . l:g.name . ';'
    call add(l:items, {
          \ 'word': l:word,
          \ 'abbr': l:word,
          \ 'menu': '0x' . get(l:g, 'addr', ''),
          \ 'kind': 'g',
          \ 'dup': 1,
          \ 'info': get(l:g, 'desc', ''),
          \ })
  endfor
  return l:items
endfunction
