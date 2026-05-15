import { useState, useEffect } from 'react';
import {
  CalendarDays, Plus, ChevronLeft, ChevronRight,
  Clock, MapPin, Users, Trash2, X, Sparkles, Link2
} from 'lucide-react';
import { fetchCalendarEvents, createCalendarEvent, deleteCalendarEvent } from '../api';
import './CalendarPage.css';

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

function CalendarPage() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newEvent, setNewEvent] = useState({ title: '', start: '', end: '', description: '', location: '', color: '#6366f1', is_all_day: false });

  useEffect(() => { loadEvents(); }, []);

  const loadEvents = async () => {
    try {
      const data = await fetchCalendarEvents();
      setEvents(data);
    } catch (err) {
      console.error('Calendar load failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newEvent.title || !newEvent.start) return;
    try {
      await createCalendarEvent({
        ...newEvent,
        end: newEvent.end || newEvent.start,
      });
      await loadEvents();
      setShowCreate(false);
      setNewEvent({ title: '', start: '', end: '', description: '', location: '', color: '#6366f1', is_all_day: false });
    } catch (err) {
      console.error('Create failed:', err);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteCalendarEvent(id);
      setEvents(events.filter(e => e.id !== id));
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  // Calendar grid
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = new Date();

  const calendarDays = [];
  for (let i = 0; i < firstDay; i++) calendarDays.push(null);
  for (let d = 1; d <= daysInMonth; d++) calendarDays.push(d);

  const getEventsForDay = (day) => {
    if (!day) return [];
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return events.filter(e => e.start?.startsWith(dateStr));
  };

  const selectedEvents = selectedDate
    ? getEventsForDay(selectedDate)
    : events.filter(e => {
        const d = new Date(e.start);
        return d >= today;
      }).sort((a, b) => new Date(a.start) - new Date(b.start)).slice(0, 10);

  const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1));

  return (
    <div className="calendar-page" id="calendar-page">
      <div className="calendar-header animate-fade-in">
        <div>
          <h1 className="calendar-title">Calendar</h1>
          <p className="calendar-subtitle">
            <Sparkles size={13} /> Calendar context feeds into AI email classification & drafting
          </p>
        </div>
        <div className="calendar-header-actions">
          <button className="btn btn-secondary" disabled title="Coming Soon">
            <Link2 size={14} /> Sync Calendar
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> New Event
          </button>
        </div>
      </div>

      <div className="calendar-body">
        {/* Month Grid */}
        <div className="calendar-grid-container animate-slide-up">
          <div className="calendar-nav">
            <button className="btn-icon" onClick={prevMonth}><ChevronLeft size={18} /></button>
            <h2 className="calendar-month">{MONTHS[month]} {year}</h2>
            <button className="btn-icon" onClick={nextMonth}><ChevronRight size={18} /></button>
          </div>

          <div className="calendar-weekdays">
            {DAYS.map(d => <div key={d} className="calendar-weekday">{d}</div>)}
          </div>

          <div className="calendar-grid">
            {calendarDays.map((day, i) => {
              const dayEvents = getEventsForDay(day);
              const isToday = day && today.getDate() === day && today.getMonth() === month && today.getFullYear() === year;
              const isSelected = day === selectedDate;
              return (
                <div
                  key={i}
                  className={`calendar-cell ${!day ? 'empty' : ''} ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''}`}
                  onClick={() => day && setSelectedDate(day === selectedDate ? null : day)}
                >
                  {day && (
                    <>
                      <span className="calendar-day-num">{day}</span>
                      <div className="calendar-day-dots">
                        {dayEvents.slice(0, 3).map((ev, j) => (
                          <span key={j} className="calendar-dot" style={{ background: ev.color || '#6366f1' }} />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Events Panel */}
        <div className="calendar-events-panel animate-slide-right">
          <h3 className="section-heading">
            {selectedDate ? `Events on ${MONTHS[month]} ${selectedDate}` : 'Upcoming Events'}
          </h3>

          {selectedEvents.length === 0 && (
            <div className="events-empty-state">
              <CalendarDays size={32} />
              <p>No events {selectedDate ? 'on this day' : 'upcoming'}</p>
            </div>
          )}

          <div className="calendar-event-list">
            {selectedEvents.map((ev) => (
              <div key={ev.id} className="cal-event-card glass-card">
                <div className="cal-event-bar" style={{ background: ev.color || '#6366f1' }} />
                <div className="cal-event-body">
                  <div className="cal-event-title">{ev.title}</div>
                  {ev.description && <p className="cal-event-desc">{ev.description}</p>}
                  <div className="cal-event-meta">
                    <span className="cal-event-meta-item">
                      <Clock size={12} />
                      {ev.is_all_day
                        ? 'All day'
                        : (() => {
                            const startT = new Date(ev.start).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
                            const endT = ev.end ? new Date(ev.end).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : null;
                            return endT && endT !== startT ? `${startT} – ${endT}` : startT;
                          })()
                      }
                    </span>
                    {ev.location && (
                      <span className="cal-event-meta-item"><MapPin size={12} /> {ev.location}</span>
                    )}
                    {ev.attendees?.length > 0 && (
                      <span className="cal-event-meta-item"><Users size={12} /> {ev.attendees.length}</span>
                    )}
                  </div>
                  {ev.attendees?.length > 0 && (
                    <div className="cal-event-attendees">
                      {ev.attendees.map((a, i) => (
                        <span key={i} className="cal-attendee-chip">{a.split('@')[0]}</span>
                      ))}
                    </div>
                  )}
                </div>
                <button className="btn-icon cal-event-delete" onClick={() => handleDelete(ev.id)} title="Delete">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal-content animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Create Event</h3>
              <button className="btn-icon" onClick={() => setShowCreate(false)}><X size={18} /></button>
            </div>
            <div className="modal-body">
              <label className="form-label">Title *</label>
              <input className="input" value={newEvent.title} onChange={e => setNewEvent({...newEvent, title: e.target.value})} placeholder="Event title" />

              <div className="form-row">
                <label className="form-checkbox">
                  <input type="checkbox" checked={newEvent.is_all_day} onChange={e => setNewEvent({...newEvent, is_all_day: e.target.checked})} />
                  <span>All-day event</span>
                </label>
              </div>

              {newEvent.is_all_day ? (
                <>
                  <label className="form-label">Date *</label>
                  <input className="input" type="date" value={newEvent.start?.split('T')[0] || ''} onChange={e => setNewEvent({...newEvent, start: e.target.value + 'T00:00', end: e.target.value + 'T23:59'})} />
                </>
              ) : (
                <>
                  <label className="form-label">Start Date/Time *</label>
                  <input className="input" type="datetime-local" value={newEvent.start} onChange={e => setNewEvent({...newEvent, start: e.target.value})} />

                  <label className="form-label">End Date/Time *</label>
                  <input className="input" type="datetime-local" value={newEvent.end} onChange={e => setNewEvent({...newEvent, end: e.target.value})} />
                </>
              )}

              <label className="form-label">Location</label>
              <input className="input" value={newEvent.location} onChange={e => setNewEvent({...newEvent, location: e.target.value})} placeholder="Room / Link" />

              <label className="form-label">Description</label>
              <textarea className="input" value={newEvent.description} onChange={e => setNewEvent({...newEvent, description: e.target.value})} placeholder="Optional details" rows={3} />

              <label className="form-label">Color</label>
              <div className="color-picker">
                {['#6366f1','#f43f5e','#f97316','#22c55e','#06b6d4','#fbbf24','#8b5cf6'].map(c => (
                  <button key={c} className={`color-swatch ${newEvent.color === c ? 'active' : ''}`} style={{ background: c }} onClick={() => setNewEvent({...newEvent, color: c})} />
                ))}
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate} disabled={!newEvent.title || !newEvent.start || (!newEvent.is_all_day && !newEvent.end)}>Create Event</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CalendarPage;
