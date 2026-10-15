/* Filtros de columna estilo Excel - widget compartido (especiales, general y recaudo) */
(function(){
  'use strict';

  var NONE = '__NINGUNA__';
  var ICONO = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="4" y1="6" x2="20" y2="6"/><line x1="7" y1="12" x2="17" y2="12"/><line x1="10" y1="18" x2="14" y2="18"/></svg>';

  var instancias = [];      // configuraciones por tabla
  var panel = null, lista = null, buscador = null;
  var instAbierta = null;   // instancia a la que pertenece el panel abierto
  var btnAbierto = null;
  var raf = 0;
  var escuchaLista = false; // evita registrar el handler de clic más de una vez

  function estadoInstancia(inst){
    if (!inst.cache){
      inst.cache = null;
      inst.filtroExacto = {};   // col -> Set de valores permitidos (si contiene NONE => ninguno)
      inst.busquedaTexto = {};  // col -> substring en minusculas
    }
    return inst;
  }

  function filas(inst){ return document.querySelectorAll(inst.bodySel + ' tr'); }

  function construirCache(inst){
    var filaCache = [];
    Array.from(filas(inst)).forEach(function(tr){
      var vals = new Array(inst.cols);
      for (var i = 0; i < inst.cols; i++){
        var cell = tr.children[i];
        var t = cell ? cell.textContent.trim() : '';
        vals[i] = t === '' ? '(vac\u00edo)' : t;
      }
      filaCache.push({ tr: tr, vals: vals });
    });
    inst.cache = filaCache;
  }

  function valoresUnicos(inst, col){
    if (!inst.cache) construirCache(inst);
    var m = new Map();
    inst.cache.forEach(function(f){ m.set(f.vals[col], (m.get(f.vals[col])||0) + 1); });
    return m;
  }

  function matchea(inst, f){
    for (var col in inst.busquedaTexto){
      if (f.vals[col].toLowerCase().indexOf(inst.busquedaTexto[col]) === -1) return false;
    }
    for (var col2 in inst.filtroExacto){
      if (inst.filtroExacto[col2].has(NONE)) return false;
      if (!inst.filtroExacto[col2].has(f.vals[col2])) return false;
    }
    return true;
  }

  function aplicarFiltros(){
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(ejecutarFiltros);
  }

  function ejecutarFiltros(){
    instancias.forEach(function(inst){
      if (!inst.cache) construirCache(inst);
      var visibles = 0;
      inst.cache.forEach(function(f){
        var ok = matchea(inst, f);
        var d = ok ? '' : 'none';
        if (f.tr.style.display !== d) f.tr.style.display = d;
        if (ok) visibles++;
      });
      if (inst.countEl){
        var el = document.getElementById(inst.countEl);
        if (el) el.textContent = '\u00b7 ' + visibles + ' de ' + inst.cache.length + ' cuentas';
      }
      var body = document.querySelector(inst.bodySel);
      var tabla = body ? body.closest('table') : null;
      if (tabla){
        tabla.querySelectorAll('.flt-btn[data-col]').forEach(function(b){
          var c = parseInt(b.dataset.col, 10);
          var activo = (inst.filtroExacto[c] && inst.filtroExacto[c].size > 0) || !!inst.busquedaTexto[c];
          b.classList.toggle('btn-warning', activo);
          b.classList.toggle('btn-light', !activo);
          var ic = b.querySelector('i');
          if (ic) ic.className = activo ? 'bi bi-funnel-fill' : 'bi bi-funnel';
        });
      }
    });
  }

  function sincronizar(){
    if (!btnAbierto || !instAbierta) return;
    var col = parseInt(btnAbierto.dataset.col, 10);
    var checks = Array.from(lista.querySelectorAll('input:checked'));
    var total = lista.querySelectorAll('input').length;
    if (checks.length === 0){
      instAbierta.filtroExacto[col] = new Set([NONE]);
    } else if (checks.length === total){
      delete instAbierta.filtroExacto[col];
    } else {
      instAbierta.filtroExacto[col] = new Set(checks.map(function(c){ return c.value; }));
    }
    aplicarFiltros();
  }

  function onBuscar(){
    if (!btnAbierto || !instAbierta) return;
    var col = parseInt(btnAbierto.dataset.col, 10);
    var q = buscador.value.trim().toLowerCase();
    if (q) instAbierta.busquedaTexto[col] = q; else delete instAbierta.busquedaTexto[col];
    Array.from(lista.children).forEach(function(item){
      item.style.display = String(item.dataset.valor||'').toLowerCase().indexOf(q) !== -1 ? '' : 'none';
    });
    aplicarFiltros();
  }

  function crearPanel(){
    panel = document.createElement('div');
    panel.id = 'fltPanel';
    panel.className = 'd-none shadow';
    panel.style.cssText = 'position:fixed;z-index:3000;width:250px;max-width:82vw;background:#FFFFFF;border:1px solid #BFBFBF;border-radius:8px;font-size:0.9rem;';
    panel.innerHTML =
      '<div class="d-flex justify-content-between align-items-center px-2 py-1 border-bottom" style="background:#EAE88C;border-radius:8px 8px 0 0;">' +
        '<b class="small"><span id="fltTitulo"></span></b>' +
        '<div class="d-flex align-items-center">' +
          '<button type="button" class="btn btn-sm btn-link py-0" data-act="todos">Todos</button>' +
          '<button type="button" class="btn btn-sm btn-link py-0 text-danger" data-act="ninguno">Ninguno</button>' +
          '<button type="button" class="btn-close ms-1" data-act="close" style="font-size:0.6rem;"></button>' +
        '</div>' +
      '</div>' +
      '<div class="p-2">' +
        '<input type="text" class="form-control form-control-sm mb-2" placeholder="Buscar valor... filtra la tabla">' +
        '<div class="flt-list" style="max-height:260px;overflow:auto;"></div>' +
        '<div class="d-flex gap-1 mt-2">' +
          '<button type="button" class="btn btn-sm btn-outline-secondary flex-fill" data-act="limpiar">Limpiar</button>' +
          '<button type="button" class="btn btn-sm btn-primary flex-fill" data-act="apply">Aplicar</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(panel);
    lista = panel.querySelector('.flt-list');
    buscador = panel.querySelector('input');
    buscador.addEventListener('input', onBuscar);
    panel.addEventListener('click', function(e){
      var b = e.target && e.target.closest ? e.target.closest('[data-act]') : null;
      if (!b) return;
      var act = b.dataset.act;
      if (act === 'todos'){
        lista.querySelectorAll('input').forEach(function(c){ c.checked = true; });
        sincronizar();
      } else if (act === 'ninguno'){
        lista.querySelectorAll('input').forEach(function(c){ c.checked = false; });
        sincronizar();
      } else if (act === 'close' || act === 'apply'){
        cerrarPanel();
      } else if (act === 'limpiar'){
        limpiarColumna();
      }
    });
  }

  function limpiarColumna(){
    if (!btnAbierto || !instAbierta) return;
    var col = parseInt(btnAbierto.dataset.col, 10);
    delete instAbierta.filtroExacto[col];
    delete instAbierta.busquedaTexto[col];
    buscador.value = '';
    lista.querySelectorAll('input').forEach(function(c){ c.checked = true; });
    aplicarFiltros();
  }

  function abrirPanel(btn, inst){
    btnAbierto = btn;
    instAbierta = inst;
    var col = parseInt(btn.dataset.col, 10);
    if (!panel) crearPanel();
    panel.querySelector('#fltTitulo').textContent = inst.labels[col] || ('Columna ' + (col + 1));
    buscador.value = '';
    var vals = valoresUnicos(inst, col);
    var exacto = inst.filtroExacto[col];
    var sel = (exacto && !exacto.has(NONE)) ? new Set(exacto) : new Set(vals.keys());
    lista.innerHTML = '';
    Array.from(vals.keys()).sort(function(a,b){ return a.localeCompare(b,'es',{numeric:true}); }).forEach(function(v){
      var label = document.createElement('label');
      label.className = 'flt-item d-flex align-items-center px-2 py-1 rounded';
      label.dataset.valor = v;
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.className = 'form-check-input m-0'; cb.value = v; cb.checked = sel.has(v);
      cb.addEventListener('change', sincronizar);
      var txt = document.createElement('span');
      txt.className = 'ms-2 flex-grow-1'; txt.textContent = v;
      var n = document.createElement('span');
      n.className = 'badge bg-light text-dark ms-1'; n.textContent = vals.get(v);
      label.appendChild(cb); label.appendChild(txt); label.appendChild(n);
      lista.appendChild(label);
    });
    if (inst.busquedaTexto[col]){
      buscador.value = inst.busquedaTexto[col];
      onBuscar();
    }
    var r = btn.getBoundingClientRect();
    panel.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 258)) + 'px';
    panel.style.top = (r.bottom + 4) + 'px';
    panel.classList.remove('d-none');
  }

  function cerrarPanel(){
    if (panel) panel.classList.add('d-none');
    btnAbierto = null;
  }

  function inyectarCSS(){
    var s = document.createElement('style');
    s.textContent = '.flt-item{cursor:pointer;font-size:0.8rem;}.flt-item:hover{background:#F2F2F2;}.flt-btn{border:1px solid #BFBFBF;padding:0 .35rem;line-height:1;}';
    document.head.appendChild(s);
  }

  function init(opts){
    var inst = estadoInstancia(opts);
    instancias.push(inst);
    if (!escuchaLista){
      escuchaLista = true;
      inyectarCSS();
      document.addEventListener('click', function(e){
        var b = e.target && e.target.closest ? e.target.closest('.flt-btn[data-col]') : null;
        if (b){
          var misma = btnAbierto && btnAbierto === b && panel && !panel.classList.contains('d-none');
          if (misma){ cerrarPanel(); return; }
          // Encontrar la instancia a la que pertenece el boton (misma tabla)
          var tablaBtn = b.closest('table');
          var instA = null;
          instancias.forEach(function(x){
            var body = document.querySelector(x.bodySel);
            var tablaBody = body ? body.closest('table') : null;
            if (tablaBody === tablaBtn) instA = x;
          });
          if (!instA) instA = instancias[instancias.length - 1];
          abrirPanel(b, instA);
          return;
        }
        if (panel && !panel.classList.contains('d-none')){
          if (e.target && e.target.closest && e.target.closest('#fltPanel')) return;
          cerrarPanel();
        }
      });
    }
    aplicarFiltros();
  }

  window.initColumnFilters = init;
})();