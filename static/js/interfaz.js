document.addEventListener('DOMContentLoaded', function () {
    completarMigaDesdeTitulo();
    mostrarAvisosFlotantes();
    indicarGuardadoEnFormularios();
    agregarIconosDeEstado();
    mejorarEstadosVacios();
});

function completarMigaDesdeTitulo() {
    const miga = document.querySelector('[data-miga-titulo]');
    if (!miga) return;
    const titulo = document.title.split(/ [-—|] /)[0].trim();
    const anterior = miga.previousElementSibling;
    if (!titulo || (anterior && anterior.textContent.trim() === titulo)) {
        miga.remove();
        if (anterior) {
            anterior.classList.add('active');
            anterior.setAttribute('aria-current', 'page');
        }
        return;
    }
    miga.textContent = titulo;
}

function mostrarAvisosFlotantes() {
    const avisos = document.querySelectorAll('.alert-dismissible.alert-success, .alert-dismissible.alert-info');
    if (!avisos.length) return;
    const contenedor = document.createElement('div');
    contenedor.className = 'avisos-flotantes';
    contenedor.setAttribute('aria-live', 'polite');
    document.body.appendChild(contenedor);
    avisos.forEach(function (aviso) {
        if (aviso.closest('.modal')) return;
        contenedor.appendChild(aviso);
        aviso.classList.add('shadow');
        setTimeout(function () {
            if (document.body.contains(aviso)) bootstrap.Alert.getOrCreateInstance(aviso).close();
        }, 4000);
    });
}

function indicarGuardadoEnFormularios() {
    document.querySelectorAll('form').forEach(function (formulario) {
        if ((formulario.getAttribute('method') || 'get').toLowerCase() !== 'post') return;
        formulario.addEventListener('submit', function (evento) {
            setTimeout(function () {
                if (evento.defaultPrevented) return;
                const botones = Array.from(formulario.querySelectorAll('button[type="submit"], button:not([type]), input[type="submit"]'));
                if (formulario.id) botones.push(...document.querySelectorAll('[form="' + formulario.id + '"]'));
                botones.forEach(function (boton) {
                    if (boton.disabled) return;
                    boton.dataset.textoOriginal = boton.innerHTML;
                    boton.disabled = true;
                    const texto = /guardar|registrar|crear|actualizar/i.test(boton.textContent) ? 'Guardando…' : 'Procesando…';
                    if (boton.tagName === 'BUTTON') {
                        boton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>' + texto;
                    }
                });
                setTimeout(function () { restaurarBotones(formulario); }, 10000);
            }, 0);
        });
    });
    window.addEventListener('pageshow', function (evento) {
        if (evento.persisted) document.querySelectorAll('form').forEach(restaurarBotones);
    });
}

function restaurarBotones(formulario) {
    formulario.querySelectorAll('[data-texto-original]').forEach(function (boton) {
        boton.innerHTML = boton.dataset.textoOriginal;
        boton.disabled = false;
        delete boton.dataset.textoOriginal;
    });
}

const ICONOS_DE_ESTADO = {
    'pendiente': 'clock',
    'ingresado': 'inbox',
    'en proceso': 'hourglass-split',
    'revisado': 'eye',
    'con observaciones': 'chat-left-text',
    'aprobado': 'check-circle-fill',
    'aprobada': 'check-circle-fill',
    'realizado': 'check-circle-fill',
    'finalizada': 'flag-fill',
    'rechazado': 'x-circle-fill',
    'rechazada': 'x-circle-fill',
    'no aplica': 'dash-circle',
    'vencido': 'exclamation-triangle-fill',
    'vencida': 'exclamation-triangle-fill',
};

function agregarIconosDeEstado() {
    document.querySelectorAll('.badge').forEach(function (etiqueta) {
        if (etiqueta.querySelector('i')) return;
        const icono = ICONOS_DE_ESTADO[etiqueta.textContent.trim().toLowerCase()];
        if (icono) etiqueta.insertAdjacentHTML('afterbegin', '<i class="bi bi-' + icono + ' me-1" aria-hidden="true"></i>');
    });
}

function mejorarEstadosVacios() {
    document.querySelectorAll('tbody > tr').forEach(function (fila) {
        if (fila.parentElement.rows.length !== 1 || fila.cells.length !== 1 || fila.cells[0].colSpan < 2) return;
        const celda = fila.cells[0];
        if (celda.querySelector('.estado-vacio')) return;
        const mensaje = celda.innerHTML.trim();
        celda.innerHTML = '<div class="estado-vacio"><i class="bi bi-inbox" aria-hidden="true"></i><div>' + mensaje + '</div></div>';
    });
}
