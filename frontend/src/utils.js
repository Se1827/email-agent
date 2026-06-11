/**
 * Format an ISO timestamp into a short, readable date string.
 * Shows time if today, "Yesterday" if yesterday, otherwise "May 7".
 */
export function formatDate(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;
    const oneDay = 86400000;

    if (diff < oneDay && date.getDate() === now.getDate()) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    if (diff < 2 * oneDay) {
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (date.getDate() === yesterday.getDate()) {
            return 'Yesterday';
        }
    }

    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/**
 * Extract a short display name from an email address.
 * "alice.smith@company.com" -> "Alice Smith"
 * "noreply@techdigest.io" -> "noreply@techdigest.io"
 */
export function formatSender(email) {
    const local = email.split('@')[0];
    // If it looks like a real name (has dots or underscores), format it
    if (/[._-]/.test(local) && local !== 'noreply' && local !== 'no-reply') {
        return local
            .split(/[._-]/)
            .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
            .join(' ');
    }
    return email;
}

/**
 * Generate a deterministic HSL color from a sender's email address.
 * Used for avatar backgrounds.
 */
export function senderColor(email) {
    let hash = 0;
    for (let i = 0; i < email.length; i++) {
        hash = email.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hue = Math.abs(hash) % 360;
    return `hsl(${hue}, 55%, 45%)`;
}

/**
 * Format a full date-time for display in detail views.
 */
export function formatFullDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleDateString([], {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

/* ── Brand & Scenario Detection ─────────────────────────────────────────── */

/**
 * Detect email scenario/type for smart card rendering.
 */
export function detectScenario(email) {
    if (!email) return 'default';
    const hay = `${email.subject || ''} ${email.body || ''}`.toLowerCase();
    const sender = (email.sender || '').toLowerCase();

    if (/flight|pnr|boarding pass|airline|e-ticket|booking ref|seat number/.test(hay))
        return 'flight';
    if (/\b(meeting|meet\.google|zoom|teams\.microsoft|webex|calendar invite|video call|conference call|join the call|sprint planning|standup|calendar|invite|appointment|schedule change)\b/.test(hay))
        return 'meeting';
    if (/\b(postponed|deadline extended|extended till|rescheduled|cancelled|no longer required|extra time|approved)\b/.test(hay))
        return 'goodnews';
    if (/\b(invoice|payment|bank account|routing number|wire transfer|receipt|transaction|bill|due amount|amount due|payment details)\b/.test(hay))
        return 'finance';
    if (/\b(code review|pull request|github|gitlab|commit|merge request|bitbucket|repository|pr #|auth-service)\b/.test(hay))
        return 'code';
    if (/\b(review|okr|self-assessment|appraisal|performance|deadline|due date|eval|mandatory training|training)\b/.test(hay))
        return 'task';
    if (/\b(spam|congratulations|won a|gift card|lucky winner|click here|totallylegit.biz|prize|claim your prize)\b/.test(hay))
        return 'spam';
    if (/\b(newsletter|digest|weekly|roundup|subscription|unsubscribe|this week in)\b/.test(hay))
        return 'newsletter';
    if (/registrar|kiit|result|exam schedule|admit card|portal|fee due|university notice|official notice|urgent|outage|failure|down|broken|fail/.test(hay) ||
        /registrar|admin@|noreply@kiit|\.edu\.in/.test(sender))
        return 'alert';
    return 'default';
}

/**
 * Detect a brand accent color from email content.
 */
export function detectBrandColor(email) {
    const hay = `${email.subject || ''} ${email.sender || ''} ${email.body || ''}`.toLowerCase();

    if (/air\s?india|airindia/.test(hay))         return { accent: '#b45309', bg: 'rgba(180,83,9,0.08)',   border: 'rgba(180,83,9,0.22)'   };
    if (/indigo|6e-/.test(hay))                   return { accent: '#4338ca', bg: 'rgba(67,56,202,0.08)',  border: 'rgba(67,56,202,0.22)'  };
    if (/spicejet/.test(hay))                     return { accent: '#b91c1c', bg: 'rgba(185,28,28,0.08)',  border: 'rgba(185,28,28,0.22)'  };
    if (/vistara/.test(hay))                      return { accent: '#7c3aed', bg: 'rgba(124,58,237,0.08)', border: 'rgba(124,58,237,0.22)' };
    if (/go\s?first|goair/.test(hay))             return { accent: '#0369a1', bg: 'rgba(3,105,161,0.08)',  border: 'rgba(3,105,161,0.22)'  };
    if (/akasa/.test(hay))                        return { accent: '#d97706', bg: 'rgba(217,119,6,0.08)',  border: 'rgba(217,119,6,0.22)'  };
    if (/emirates/.test(hay))                     return { accent: '#9f1239', bg: 'rgba(159,18,57,0.08)',  border: 'rgba(159,18,57,0.22)'  };
    if (/singapore airlines/.test(hay))           return { accent: '#1e40af', bg: 'rgba(30,64,175,0.08)',  border: 'rgba(30,64,175,0.22)'  };
    if (/zoom\.us|zoom meeting/.test(hay))        return { accent: '#1d4ed8', bg: 'rgba(29,78,216,0.08)',  border: 'rgba(29,78,216,0.22)'  };
    if (/teams\.microsoft|microsoft teams/.test(hay)) return { accent: '#5b21b6', bg: 'rgba(91,33,182,0.08)', border: 'rgba(91,33,182,0.22)' };
    if (/meet\.google|google meet/.test(hay))     return { accent: '#15803d', bg: 'rgba(21,128,61,0.08)',  border: 'rgba(21,128,61,0.22)'  };
    if (/webex/.test(hay))                        return { accent: '#075985', bg: 'rgba(7,89,133,0.08)',   border: 'rgba(7,89,133,0.22)'   };
    if (/kiit|kalinga/.test(hay))                 return { accent: '#166534', bg: 'rgba(22,101,52,0.08)',  border: 'rgba(22,101,52,0.22)'  };
    if (/iit|indian institute of tech/.test(hay)) return { accent: '#0c4a6e', bg: 'rgba(12,74,110,0.08)',  border: 'rgba(12,74,110,0.22)'  };
    if (/nit /.test(hay))                         return { accent: '#7c2d12', bg: 'rgba(124,45,18,0.08)',  border: 'rgba(124,45,18,0.22)'  };
    if (/capgemini/.test(hay))                    return { accent: '#1e40af', bg: 'rgba(30,64,175,0.08)',  border: 'rgba(30,64,175,0.22)'  };
    if (/infosys/.test(hay))                      return { accent: '#065f46', bg: 'rgba(6,95,70,0.08)',    border: 'rgba(6,95,70,0.22)'    };
    if (/tcs|tata consultancy/.test(hay))         return { accent: '#1e3a5f', bg: 'rgba(30,58,95,0.08)',   border: 'rgba(30,58,95,0.22)'   };
    return null;
}

export const SCENARIO_DEFAULTS = {
    flight:     { accent: '#0ea5e9', bg: 'rgba(14,165,233,0.08)',  border: 'rgba(14,165,233,0.22)'  },
    meeting:    { accent: '#a78bfa', bg: 'rgba(167,139,250,0.08)', border: 'rgba(167,139,250,0.22)' },
    goodnews:   { accent: '#10b981', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.22)'  },
    alert:      { accent: '#f59e0b', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.22)'  },
    finance:    { accent: '#10b981', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.22)'  },
    code:       { accent: '#818cf8', bg: 'rgba(129,140,248,0.08)', border: 'rgba(129,140,248,0.22)' },
    task:       { accent: '#f43f5e', bg: 'rgba(244,63,94,0.08)',   border: 'rgba(244,63,94,0.22)'   },
    spam:       { accent: '#ef4444', bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.22)'   },
    newsletter: { accent: '#06b6d4', bg: 'rgba(6,182,212,0.08)',   border: 'rgba(6,182,212,0.22)'   },
    default:    { accent: '#6366f1', bg: 'rgba(99,102,241,0.08)',  border: 'rgba(99,102,241,0.22)'  },
};

export function getBrandTheme(email, scenario) {
    const brand = detectBrandColor(email);
    return brand || SCENARIO_DEFAULTS[scenario] || SCENARIO_DEFAULTS.default;
}
