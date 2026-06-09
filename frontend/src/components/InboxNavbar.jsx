import { Search, RefreshCw, Zap, Inbox, Star, AlertTriangle, FileEdit, Mail, Send } from 'lucide-react';
import './InboxNavbar.css';

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

function InboxNavbar({
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
    accountSwitcher, // injected from InboxPage
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
        <nav className="inbox-navbar" id="inbox-navbar">
            <div className="navbar-top-row">
                <div className="navbar-brand">
                    <Inbox size={22} className="brand-icon" />
                    <h2 className="navbar-title">EmailAgent</h2>
                </div>

                <div className="navbar-tabs">
                    {FOLDERS.map(({ id, label, icon: Icon }) => {
                        const count = id === 'unread' ? unreadCount
                            : id === 'starred' ? starredCount
                            : id === 'sent' ? sentCount
                            : null;
                        return (
                            <button
                                key={id}
                                className={`navbar-tab ${filters.folder === id ? 'active' : ''}`}
                                onClick={() => setFolder(id)}
                            >
                                <Icon size={16} />
                                <span className="tab-label">{label}</span>
                                {count > 0 && <span className="tab-count">{count}</span>}
                            </button>
                        );
                    })}
                </div>

                <div className="navbar-actions">
                    <div className="navbar-search-wrapper">
                        <Search size={14} className="navbar-search-icon" />
                        <input
                            type="text"
                            className="navbar-search-input"
                            placeholder="Search emails..."
                            value={searchQuery}
                            onChange={(e) => onSearchChange(e.target.value)}
                        />
                    </div>
                    
                    <button
                        className="btn-icon nav-action-btn"
                        onClick={onRefresh}
                        disabled={!!busyAction}
                        title="Refresh Inbox"
                    >
                        <RefreshCw size={16} className={busyAction === 'refresh' ? 'spin' : ''} />
                    </button>
                    
                    <button
                        className="btn-icon nav-action-btn primary"
                        onClick={onClassifyAll}
                        disabled={!!busyAction}
                        title="Classify All"
                    >
                        <Zap size={16} />
                    </button>
                    
                    <div className="navbar-account-slot">
                        {accountSwitcher}
                    </div>
                </div>
            </div>

            <div className="navbar-bottom-row">
                <div className="navbar-filter-group">
                    <span className="filter-label">Priority:</span>
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

                <div className="navbar-filter-group">
                    <span className="filter-label">Category:</span>
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
                    <button className="btn-link clear-filters-btn" onClick={clearFilters}>
                        Clear Filters
                    </button>
                )}
                
                <div className="navbar-stats-spacer"></div>
                <span className="navbar-stats">
                    {classifiedCount}/{emailCount} classified
                </span>
            </div>
        </nav>
    );
}

export default InboxNavbar;
