import './Sidebar.css';

const PRIORITIES = ['critical', 'high', 'normal', 'low'];
const CATEGORIES = [
    { value: 'meeting', label: 'Meeting' },
    { value: 'deadline', label: 'Deadline' },
    { value: 'info', label: 'Info' },
    { value: 'action-required', label: 'Action Required' },
    { value: 'spam', label: 'Spam' },
];

function Sidebar({
    filters,
    onFiltersChange,
    onRefresh,
    onClassifyAll,
    busyAction,
    emailCount,
    classifiedCount,
}) {
    const togglePriority = (p) => {
        const current = filters.priority;
        const next = current.includes(p)
            ? current.filter((x) => x !== p)
            : [...current, p];
        onFiltersChange({ ...filters, priority: next });
    };

    const toggleCategory = (c) => {
        const current = filters.category;
        const next = current.includes(c)
            ? current.filter((x) => x !== c)
            : [...current, c];
        onFiltersChange({ ...filters, category: next });
    };

    const clearFilters = () => {
        onFiltersChange({ priority: [], category: [] });
    };

    const hasFilters = filters.priority.length > 0 || filters.category.length > 0;

    return (
        <aside className="sidebar">
            <div className="sidebar-header">
                <h1 className="sidebar-title">Email Agent</h1>
                <span className="sidebar-stats">
                    {classifiedCount}/{emailCount} classified
                </span>
            </div>

            <div className="sidebar-actions">
                <button
                    className="btn btn-primary"
                    onClick={onRefresh}
                    disabled={!!busyAction}
                >
                    {busyAction === 'refresh' ? 'Fetching...' : 'Refresh Inbox'}
                </button>
                <button
                    className="btn btn-secondary"
                    onClick={onClassifyAll}
                    disabled={!!busyAction}
                >
                    {busyAction === 'classify-all' ? 'Classifying...' : 'Classify All'}
                </button>
            </div>

            <div className="sidebar-section">
                <h3 className="sidebar-section-title">Priority</h3>
                <div className="filter-chips">
                    {PRIORITIES.map((p) => (
                        <button
                            key={p}
                            className={`chip chip-priority-${p} ${filters.priority.includes(p) ? 'chip-active' : ''
                                }`}
                            onClick={() => togglePriority(p)}
                        >
                            {p}
                        </button>
                    ))}
                </div>
            </div>

            <div className="sidebar-section">
                <h3 className="sidebar-section-title">Category</h3>
                <div className="filter-chips">
                    {CATEGORIES.map(({ value, label }) => (
                        <button
                            key={value}
                            className={`chip chip-category ${filters.category.includes(value) ? 'chip-active' : ''
                                }`}
                            onClick={() => toggleCategory(value)}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {hasFilters && (
                <button className="btn-link" onClick={clearFilters}>
                    Clear filters
                </button>
            )}
        </aside>
    );
}

export default Sidebar;
