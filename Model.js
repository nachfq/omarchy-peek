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
                || !Array.isArray(table.rows)) throw new Error('Invalid table');
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

// A single virtualized list keeps large snapshots responsive. Filtering never
// starts a collector and only searches the displayed string cells.
function rows(snapshot, filter) {
    if (!snapshot) return [];
    var result = [];
    var query = filter.trim().toLowerCase();
    snapshot.notes.forEach(function(note) { result.push({kind: 'note', text: note, cells: []}); });
    snapshot.tables.forEach(function(table) {
        var matches = table.rows.filter(function(row) {
            return !query || table.columns.some(function(column) {
                return row[column.key].toLowerCase().indexOf(query) >= 0;
            });
        });
        result.push({kind: 'title', text: table.title + ' · ' + matches.length + ' / ' + table.rows.length, cells: []});
        result.push({kind: 'header', text: '', cells: table.columns.map(function(c) { return c.label; })});
        if (!matches.length) result.push({kind: 'empty', text: query ? 'No matching rows.' : 'No entries.', cells: []});
        matches.forEach(function(row) {
            result.push({kind: 'row', text: '', cells: table.columns.map(function(c) { return row[c.key]; })});
        });
    });
    if (!snapshot.tables.length) result.push({kind: 'empty', text: 'No tables returned.', cells: []});
    return result;
}
