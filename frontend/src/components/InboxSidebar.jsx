import { Search, RefreshCw, Zap, Inbox, Star, AlertTriangle, FileEdit, Mail, Send } from 'lucide-react';
import './InboxSidebar.css';

const PRIORITIES = ['critical', 'high', 'normal', 'low'];
const CATEGORIES = [
    { value: 'meeting', label: 'Meeting' },
    { value: 'deadline', label: 'Deadline' },
    { value: 'info', label: 'Info' },
    { value: 'action-required', label: 'Action Required' },
    { value: 'spam', label: 'Spam' },
];

const FOLDERS = [
    { id: 'all', label: 'All Mail', icon: Inbox },
    { id: 'unread', label: 'Unread', icon: Mail },
    { id: 'starred', label: 'Starred', icon: Star },
    { id: 'critical', label: 'Urgent', icon: AlertTriangle },
    { id: 'drafts', label: 'Has Draft', icon: FileEdit },
    { id: 'sent', label: 'Sent', icon: Send },
];

function InboxSidebar({
    filters,
    onFiltersChange,
    onRefresh,
    onClassifyAll,
    busyAction,
    emailCount,
    classifiedCount,
    unreadCount,
    starredCount,
    sentCount = 0,
    searchQuery,
    onSearchChange,
}) {
    const togglePriority = (p) => {
        const current = filters.priority;
        const next = current.includes(p) ? current.filter((x) => x !== p) : [...current, p];
        onFiltersChange({ ...filters, priority: next });
    };

    const toggleCategory = (c) => {
        const current = filters.category;
        const next = current.includes(c) ? current.filter((x) => x !== c) : [...current, c];
        onFiltersChange({ ...filters, category: next });
    };

    const setFolder = (f) => {
        onFiltersChange({ ...filters, folder: f });
    };

    const clearFilters = () => {
        onFiltersChange({ priority: [], category: [], folder: 'all' });
        onSearchChange('');
    };

    const hasFilters = filters.priority.length > 0 || filters.category.length > 0 || searchQuery;

    return (
        <aside className="inbox-sidebar" id="inbox-sidebar">
            <div className="inbox-sidebar-header">
                <h2 className="inbox-sidebar-title">Inbox</h2>
                <span className="inbox-sidebar-stats">
                    {classifiedCount}/{emailCount} classified
                </span>
            </div>

            {/* Search */}
            <div className="inbox-search-wrapper">
                <Search size={14} className="inbox-search-icon" />
                <input
                    type="text"
                    className="inbox-search-input"
                    placeholder="Search emails..."
                    value={searchQuery}
                    onChange={(e) => onSearchChange(e.target.value)}
                    id="inbox-search"
                />
            </div>

            {/* Actions */}
            <div className="inbox-sidebar-actions">
                <button
                    className="btn btn-primary"
                    onClick={onRefresh}
                    disabled={!!busyAction}
                    style={{ flex: 1 }}
                >
                    <RefreshCw size={14} className={busyAction === 'refresh' ? 'spin' : ''} />
                    {busyAction === 'refresh' ? 'Fetching...' : 'Refresh'}
                </button>
                <button
                    className="btn btn-secondary"
                    onClick={onClassifyAll}
                    disabled={!!busyAction}
                    style={{ flex: 1 }}
                >
                    <Zap size={14} />
                    {busyAction === 'classify-all' ? 'Working...' : 'Classify All'}
                </button>
            </div>

            {/* Smart Folders */}
            <div className="inbox-sidebar-section">
                <h3 className="section-heading">Folders</h3>
                <div className="folder-list">
                    {FOLDERS.map(({ id, label, icon: Icon }) => {
                        const count = id === 'unread' ? unreadCount
                            : id === 'starred' ? starredCount
                            : id === 'sent' ? sentCount
                            : null;
                        return (
                            <button
                                key={id}
                                className={`folder-item ${filters.folder === id ? 'folder-active' : ''}`}
                                onClick={() => setFolder(id)}
                            >
                                <Icon size={15} />
                                <span className="folder-label">{label}</span>
                                {count > 0 && <span className="folder-count">{count}</span>}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Priority Filter */}
            <div className="inbox-sidebar-section">
                <h3 className="section-heading">Priority</h3>
                <div className="filter-chips">
                    {PRIORITIES.map((p) => (
                        <button
                            key={p}
                            className={`chip chip-priority-${p} ${filters.priority.includes(p) ? 'chip-active' : ''}`}
                            onClick={() => togglePriority(p)}
                        >
                            {p}
                        </button>
                    ))}
                </div>
            </div>

            {/* Category Filter */}
            <div className="inbox-sidebar-section">
                <h3 className="section-heading">Category</h3>
                <div className="filter-chips">
                    {CATEGORIES.map(({ value, label }) => (
                        <button
                            key={value}
                            className={`chip chip-category ${filters.category.includes(value) ? 'chip-active' : ''}`}
                            onClick={() => toggleCategory(value)}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {hasFilters && (
                <button className="btn-link" onClick={clearFilters}>
                    Clear all filters
                </button>
            )}
        </aside>
    );
}

export default InboxSidebar;
