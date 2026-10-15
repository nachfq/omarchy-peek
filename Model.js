.pragma library

var sections = ['docker', 'services', 'processes', 'worktrees', 'disk'];
var labels = ['Docker', 'Services', 'Processes', 'Worktrees', 'Disk'];

function options(settings) {
    var result = {};
    ['repositoryRoots', 'diskPaths', 'discoveryDepth'].forEach(function(key) {
        if (settings && settings[key] !== undefined) result[key] = settings[key];
    });
    return result;
}

function parse(text, section) {
    var data = JSON.parse(text);
    if (!data || data.schemaVersion !== 1 || data.section !== section
            || ['ok', 'partial', 'error'].indexOf(data.status) < 0
            || typeof data.collectedAt !== 'string' || !data.collectedAt
            || typeof data.summary !== 'string' || !Array.isArray(data.tables)
            || !Array.isArray(data.notes)) throw new Error('Invalid snapshot');
    data.notes.forEach(function(note) {
        if (typeof note !== 'string') throw new Error('Invalid note');
    });
    data.tables.forEach(function(table) {
        if (!table || typeof table.id !== 'string' || typeof table.title !== 'string'
                || !Array.isArray(table.columns) || table.columns.length === 0
                || !Array.isArray(table.rows)
                || (table.status !== undefined && ['ok', 'partial', 'error'].indexOf(table.status) < 0)) throw new Error('Invalid table');
        table.columns.forEach(function(column) {
            if (!column || typeof column.key !== 'string' || typeof column.label !== 'string')
                throw new Error('Invalid column');
        });
        table.rows.forEach(function(row) {
            if (!row || typeof row !== 'object') throw new Error('Invalid row');
            table.columns.forEach(function(column) {
                if (typeof row[column.key] !== 'string') throw new Error('Invalid cell');
            });
        });
    });
    return data;
}

function table(snapshot, id) {
    return snapshot ? snapshot.tables.filter(function(t) { return t.id === id; })[0] || null : null;
}
function coverage(snapshot, t) { return t ? t.status || snapshot.status : 'error'; }
function count(snapshot, id, predicate) {
    var t = table(snapshot, id);
    if (!t || coverage(snapshot, t) === 'error') return 'Unavailable';
    var n = t.rows.filter(predicate || function() { return true; }).length;
    if (!n && coverage(snapshot, t) === 'partial') return 'Unknown';
    return (coverage(snapshot, t) === 'partial' ? '≥ ' : '') + n;
}
function bytes(value, measurement) {
    if (measurement === 'unavailable' || value === '' || !isFinite(Number(value))) return 'Not measured';
    var n = Number(value), units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'], i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (measurement === 'partial' ? '≥ ' : '') + (i ? n.toFixed(n >= 10 ? 1 : 2) : n) + ' ' + units[i];
}
function dockerSize(value) {
    var match = String(value).match(/^([0-9.]+)\s*([KMGT]?i?B)$/i);
    if (!match || !isFinite(Number(match[1]))) return value || 'Unavailable';
    return (Number(match[1]) === 0 ? '0' : Number(match[1]).toFixed(1)) + ' ' + match[2];
}
function sorted(rows, key) {
    return rows.slice().sort(function(a, b) {
        var av = a[key] === '' || !isFinite(Number(a[key])) ? -1 : Number(a[key]);
        var bv = b[key] === '' || !isFinite(Number(b[key])) ? -1 : Number(b[key]);
        return bv - av;
    });
}
function name(path) { return path.split('/').filter(function(p) { return !!p; }).pop() || path; }
function running(row) { return row.active === 'active' && row.sub === 'running'; }
function overview(section, snapshot, error, loading) {
    var result = {title: labels[sections.indexOf(section)], status: loading ? 'Collecting…' : error ? 'Unavailable' : snapshot ? snapshot.status === 'ok' ? 'Snapshot' : snapshot.status === 'partial' ? 'Partial' : 'Unavailable' : 'Waiting', metric: '—', label: '', lines: [], timestamp: snapshot ? snapshot.collectedAt : ''};
    if (!snapshot) { result.label = error ? 'Refresh to retry' : loading ? 'Collecting a fresh snapshot' : 'Queued for collection'; return result; }
    if (section === 'docker') {
        var usage = table(snapshot, 'usage');
        function category(type) {
            var row = usage && coverage(snapshot, usage) !== 'error' ? usage.rows.filter(function(r) { return r.Type === type; })[0] : null;
            return row ? (coverage(snapshot, usage) === 'partial' ? 'Partial · ' : '') + dockerSize(row.Size) : 'Unavailable';
        }
        result.metric = category('Images');
        result.label = 'images on disk · Docker estimate';
        result.lines = [{label: 'Volumes', value: category('Local Volumes')}, {label: 'Build cache', value: category('Build Cache')}, {label: 'Container writable', value: category('Containers')}, {label: 'Running containers', value: count(snapshot, 'containers', function(r) { return r.State === 'running'; })}];
    } else if (section === 'services') {
        result.metric = count(snapshot, 'services', function(r) { return r.scope === 'user' && running(r); });
        result.label = 'running user services';
        result.lines = [{label: 'System running', value: count(snapshot, 'services', function(r) { return r.scope === 'system' && running(r); })}, {label: 'Registered', value: count(snapshot, 'services')}];
    } else {
        var wt = table(snapshot, 'worktrees'), rows = wt && coverage(snapshot, wt) !== 'error' ? sorted(wt.rows, 'bytes') : [];
        var measured = rows.filter(function(r) { return r.measurement !== 'unavailable' && r.bytes !== '' && isFinite(Number(r.bytes)); });
        result.metric = measured.length ? bytes(measured[0].bytes, measured[0].measurement) : 'Not measured';
        result.label = 'largest observed worktree';
        result.lines = [{label: 'Registered', value: count(snapshot, 'worktrees')}, {label: 'Fully measured', value: wt && coverage(snapshot, wt) !== 'error' ? rows.filter(function(r) { return r.measurement === 'complete'; }).length + ' / ' + rows.length : 'Unavailable'}];

    }
    return result;
}
function rows(snapshot, filter, options) {
    if (!snapshot) return [];
    options = options || {};
    var result = [], query = filter.trim().toLowerCase();
    if (options.notes) snapshot.notes.forEach(function(note) { result.push({kind: 'note', text: note, secondary: '', value: '', cells: []}); });
    var tables = snapshot.tables.slice();
    if (!options.raw && snapshot.section === 'docker') tables.sort(function(a, b) { return (a.id === 'usage' ? -1 : 0) - (b.id === 'usage' ? -1 : 0); });
    tables.forEach(function(t) {
        var matches = t.rows.filter(function(row) {
            if (!options.raw && t.id === 'services') {
                if ((options.scope || 'user') !== 'all' && row.scope !== (options.scope || 'user')) return false;
                if (!options.allStates && !running(row)) return false;
            }
            return !query || t.columns.some(function(c) { return row[c.key].toLowerCase().indexOf(query) >= 0; });
        });
        if (!options.raw && snapshot.section === 'services' && t.id === 'timers') return;
        if (!options.raw && snapshot.section === 'docker' && ['containers', 'usage'].indexOf(t.id) < 0) return;
        if (t.columns.some(function(c) { return c.key === 'bytes' || c.key === 'rss'; })) matches = sorted(matches, t.id === 'processes' ? 'rss' : 'bytes');
        result.push({kind: 'title', text: t.title + ' · ' + matches.length + (coverage(snapshot, t) !== 'ok' ? ' · ' + (coverage(snapshot, t) === 'partial' ? 'Partial' : 'Unavailable') : ''), secondary: '', value: '', cells: []});
        if (!matches.length) result.push({kind: 'empty', text: coverage(snapshot, t) === 'error' ? 'Unavailable. Open notes for details.' : query || t.id === 'services' ? 'No matching rows.' : 'No entries.', secondary: '', value: '', cells: []});
        if (options.raw && matches.length) result.push({kind: 'header', text: '', secondary: '', value: '', cells: t.columns.map(function(c) { return c.label; })});
        matches.forEach(function(r) {
            if (options.raw) { result.push({kind: 'row', text: '', secondary: '', value: '', cells: t.columns.map(function(c) { return r[c.key]; })}); return; }
            var title = '', secondary = '', value = '';
            if (t.id === 'containers') { title = r.Names; secondary = r.Status + (r.Ports ? ' · ' + r.Ports : '') + (r.composeProject ? ' · ' + r.composeProject : ''); value = r.State; }
            else if (t.id === 'usage') { title = r.Type; secondary = r.TotalCount + ' total · ' + r.Active + ' active'; value = dockerSize(r.Size); }
            else if (t.id === 'services') { title = r.unit; secondary = r.description + ' · ' + r.scope + ' · ' + r.enablement; value = r.sub || r.active; }
            else if (t.id === 'worktrees') { title = name(r.path); secondary = r.branch + ' · ' + r.changes + '\n' + r.path; value = bytes(r.bytes, r.measurement); }
            else if (t.id === 'paths' || t.id === 'children') { title = name(r.path); secondary = r.path; value = bytes(r.bytes, r.measurement); }
            else if (t.id === 'processes') { title = r.name + ' · PID ' + r.pid; secondary = r.cwd; value = bytes(r.rss); }
            else { title = t.columns.slice(0, 2).map(function(c) { return r[c.key]; }).join(' · '); secondary = t.columns.slice(2).map(function(c) { return c.label + ': ' + r[c.key]; }).join(' · '); }
            result.push({kind: 'entry', text: title, secondary: secondary, value: value, cells: []});
        });
    });
    if (!snapshot.tables.length) result.push({kind: 'empty', text: snapshot.status === 'error' ? 'Unavailable. Open notes for details.' : 'No entries.', secondary: '', value: '', cells: []});
    return result;
}
