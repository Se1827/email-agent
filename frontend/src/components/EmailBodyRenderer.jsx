import React, { useEffect, useRef, useState } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';
import DOMPurify from 'dompurify';
import './EmailBodyRenderer.css';

/* ─── Helper: Detect if string is HTML ───────────────────────────────────── */
export function isHTML(text) {
  if (!text) return false;
  const trimmed = text.trim();
  return (
    trimmed.startsWith('<!DOCTYPE html') ||
    trimmed.startsWith('<html') ||
    /<\/?[a-z][\s\S]*>/i.test(text)
  );
}

/* ─── Helper: Turn URLs into clickable links ──────────────────────────────── */
function linkifyText(text, keyPrefix) {
  const urlRegex = /(https?:\/\/[^\s<>"]+)/g;
  const parts = text.split(urlRegex);
  if (parts.length === 1) return text;
  
  return parts.map((part, index) => {
    if (urlRegex.test(part)) {
      return (
        <a 
          key={`${keyPrefix}-link-${index}`} 
          href={part} 
          target="_blank" 
          rel="noopener noreferrer"
          className="email-inline-link"
        >
          {part}
        </a>
      );
    }
    return part;
  });
}

/* ─── Helper: Clean Snippet (Strips HTML tags) ───────────────────────────── */
export function cleanSnippet(text, maxLength = 90) {
  if (!text) return '';
  const trimmed = text.trim();
  if (
    trimmed.startsWith('<!DOCTYPE html') ||
    trimmed.startsWith('<html') ||
    /<\/?[a-z][\s\S]*>/i.test(text)
  ) {
    const clean = text
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    return clean.slice(0, maxLength);
  }
  return text.slice(0, maxLength).replace(/\n/g, ' ');
}

/* ─── Helper: Parse headers from email thread sections ───────────────────── */
function parseOriginalHeaders(text) {
  const lines = text.split('\n');
  const headers = {};
  let parsedCount = 0;
  
  for (let i = 0; i < Math.min(lines.length, 8); i++) {
    const line = lines[i];
    const fromMatch = line.match(/^(?:From|From\s*:)\s*(.+)$/i);
    const dateMatch = line.match(/^(?:Date|Sent|Date\s*:|Sent\s*:)\s*(.+)$/i);
    const toMatch = line.match(/^(?:To|To\s*:)\s*(.+)$/i);
    const subjectMatch = line.match(/^(?:Subject|Subject\s*:)\s*(.+)$/i);
    
    if (fromMatch) {
      headers.from = fromMatch[1].trim();
      parsedCount++;
    } else if (dateMatch) {
      headers.date = dateMatch[1].trim();
      parsedCount++;
    } else if (toMatch) {
      headers.to = toMatch[1].trim();
      parsedCount++;
    } else if (subjectMatch) {
      headers.subject = subjectMatch[1].trim();
      parsedCount++;
    }
  }
  
  if (parsedCount >= 2) {
    let headerEndIndex = 0;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/^(?:From|Sent|Date|To|Subject|Cc|Bcc)\s*:/i.test(line.trim())) {
        headerEndIndex = i + 1;
      } else if (line.trim() === '') {
        if (headerEndIndex > 0) {
          headerEndIndex = i + 1;
          break;
        }
      } else if (headerEndIndex > 0 && i > headerEndIndex + 2) {
        break;
      }
    }
    
    const bodyText = lines.slice(headerEndIndex).join('\n');
    return { headers, bodyText };
  }
  
  return null;
}

/* ─── Helper: Collapsible Original Message / Forwarded Thread ────────────── */
function CollapsibleOriginalMessage({ text }) {
  const [expanded, setExpanded] = useState(false);

  const parsed = parseOriginalHeaders(text);
  
  if (parsed) {
    const { headers, bodyText } = parsed;
    return (
      <div className="collapsible-original-email">
        <button 
          className="collapse-toggle-btn"
          onClick={() => setExpanded(!expanded)}
          type="button"
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span>Original Message / Forwarded Content</span>
        </button>
        
        <div className="collapsible-original-content-wrapper">
          <div className="email-original-headers-table">
            {headers.from && <div className="orig-header-row"><span className="orig-header-label">From:</span> <span className="orig-header-val">{headers.from}</span></div>}
            {headers.to && <div className="orig-header-row"><span className="orig-header-label">To:</span> <span className="orig-header-val">{headers.to}</span></div>}
            {headers.date && <div className="orig-header-row"><span className="orig-header-label">Date/Sent:</span> <span className="orig-header-val">{headers.date}</span></div>}
            {headers.subject && <div className="orig-header-row"><span className="orig-header-label">Subject:</span> <span className="orig-header-val">{headers.subject}</span></div>}
          </div>
          {expanded && (
            <div className="email-original-body-content animate-fade-in">
              <EmailBodyRenderer text={bodyText} />
            </div>
          )}
        </div>
      </div>
    );
  }

  const lines = text.split('\n');
  const headerPreview = lines.slice(0, 4).join('\n');
  const restOfText = lines.slice(4).join('\n');

  return (
    <div className="collapsible-original-email">
      <button 
        className="collapse-toggle-btn"
        onClick={() => setExpanded(!expanded)}
        type="button"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>Original Message / Forwarded Content</span>
      </button>
      
      <div className="collapsible-original-content-wrapper">
        <pre className="email-original-header-preview">{headerPreview}</pre>
        {expanded && (
          <div className="email-original-body-content animate-fade-in">
            <EmailBodyRenderer text={restOfText} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Helper: Parse line headers for forwards ────────────────────────────── */
const isOriginalHeader = (line, nextLines = []) => {
  const trimmed = line.trim();
  if (
    trimmed.startsWith('--- Original Message ---') ||
    trimmed.startsWith('-----Original Message-----') ||
    trimmed.startsWith('---------- Forwarded message ---------') ||
    trimmed.startsWith('----- Forwarded Message -----') ||
    /^[*-]+\s*Forwarded message\s*[*-]+/i.test(trimmed) ||
    /^On\s+.+,\s+.+\s+wrote:/i.test(trimmed)
  ) {
    return true;
  }
  
  const hasFrom = trimmed.startsWith('From:');
  if (hasFrom && nextLines.length > 0) {
    const next1 = nextLines[0]?.trim() || '';
    const next2 = nextLines[1]?.trim() || '';
    if (
      next1.startsWith('Sent:') || 
      next1.startsWith('To:') || 
      next1.startsWith('Date:') ||
      next2.startsWith('To:') ||
      next2.startsWith('Subject:')
    ) {
      return true;
    }
  }
  return false;
};

/* ─── Helper: Clean/Isolated HTML Renderer inside Iframe ─────────────────── */
function HTMLIframeRenderer({ html }) {
  const iframeRef = useRef(null);
  const [height, setHeight] = useState('100px');

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    // Sanitize HTML using DOMPurify before rendering to ensure safety
    const cleanHtml = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [
        'b', 'i', 'u', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'ul', 'ol', 'li', 'blockquote', 'div', 'span', 'p', 'h1', 'h2', 'h3',
        'h4', 'h5', 'h6', 'br', 'hr', 'style', 'font', 'center'
      ],
      ALLOWED_ATTR: [
        'href', 'src', 'alt', 'title', 'class', 'style', 'width', 'height',
        'align', 'valign', 'border', 'cellpadding', 'cellspacing', 'target'
      ],
      RETURN_TRUSTED_TYPE: false,
    });

    const doc = iframe.contentDocument || iframe.contentWindow.document;
    doc.open();
    
    // Inject email HTML with standard font/resets and force light background
    // Since HTML emails are designed for white pages, we frame them in a white card.
    doc.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <base href="${window.location.origin}/">
          <style>
            body {
              margin: 0;
              padding: 12px;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
              font-size: 14px;
              line-height: 1.5;
              color: #212529;
              background-color: #ffffff;
              box-sizing: border-box;
              word-break: break-word;
            }
            img {
              max-width: 100%;
              height: auto;
              display: block;
            }
            a {
              color: #2563eb;
              text-decoration: underline;
            }
            a:hover {
              color: #1d4ed8;
            }
            table {
              max-width: 100%;
              border-collapse: collapse;
              margin-bottom: 12px;
            }
            th, td {
              border: 1px solid #e2e8f0;
              padding: 8px 12px;
              text-align: left;
            }
            /* Scrollable container for tables to prevent breakage */
            .table-container {
              width: 100%;
              overflow-x: auto;
              margin-bottom: 16px;
              border: 1px solid #e2e8f0;
              border-radius: 6px;
              -webkit-overflow-scrolling: touch;
            }
            .table-container table {
              margin-bottom: 0;
              border: none;
            }
          </style>
        </head>
        <body>
          ${cleanHtml}
        </body>
      </html>
    `);
    doc.close();

    // Wrap table elements dynamically inside the iframe inside a scrollable table-container wrapper
    const tables = doc.querySelectorAll('table');
    tables.forEach(table => {
      if (table.parentElement && !table.parentElement.classList.contains('table-container')) {
        const wrapper = doc.createElement('div');
        wrapper.className = 'table-container';
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
      }
    });

    const updateHeight = () => {
      if (doc.body) {
        setHeight(`${doc.body.scrollHeight + 16}px`);
      }
    };

    updateHeight();

    const resizeObserver = new ResizeObserver(() => {
      updateHeight();
    });

    if (doc.body) {
      resizeObserver.observe(doc.body);
    }

    iframe.onload = updateHeight;

    return () => {
      resizeObserver.disconnect();
    };
  }, [html]);

  return (
    <iframe
      ref={iframeRef}
      style={{
        width: '100%',
        height: height,
        border: 'none',
        background: '#ffffff',
        overflow: 'hidden',
        display: 'block',
      }}
      title="HTML Email Content"
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
    />
  );
}

/* ─── Main Component: EmailBodyRenderer ──────────────────────────────────── */
export function EmailBodyRenderer({ text, isNestedQuote = false }) {
  if (!text) return null;

  // 1. If it's a styled HTML email, render it inside the isolated White Card iframe
  if (!isNestedQuote && isHTML(text)) {
    return (
      <div className="html-email-container animate-fade-in">
        <HTMLIframeRenderer html={text} />
      </div>
    );
  }

  // 2. Otherwise, parse plain text line-by-line to format quote indentations & collapsible threads
  const lines = text.split('\n');
  const elements = [];
  let currentQuoteBlock = [];
  let inQuote = false;

  const flushQuote = (key) => {
    if (currentQuoteBlock.length > 0) {
      const quoteText = currentQuoteBlock.join('\n');
      elements.push(
        <blockquote key={`quote-${key}`} className="email-quote">
          <EmailBodyRenderer text={quoteText} isNestedQuote={true} />
        </blockquote>
      );
      currentQuoteBlock = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const isQuoteLine = line.trim().startsWith('>');

    if (isQuoteLine) {
      if (!inQuote) {
        inQuote = true;
      }
      // Strip leading '>' and up to one space
      const cleanLine = line.trim().substring(1).replace(/^\s/, '');
      currentQuoteBlock.push(cleanLine);
    } else {
      if (inQuote) {
        flushQuote(i);
        inQuote = false;
      }

      // Detect original message headers or forwarded sections
      const nextLines = lines.slice(i + 1, i + 3);
      if (isOriginalHeader(line, nextLines)) {
        const remainingText = lines.slice(i).join('\n');
        elements.push(
          <CollapsibleOriginalMessage key={`orig-${i}`} text={remainingText} />
        );
        break; // Stop parsing since the collapsible component handles all remaining lines
      } else {
        elements.push(
          <div key={`line-${i}`} className="email-body-line">
            {linkifyText(line, i)}
          </div>
        );
      }
    }
  }

  if (inQuote) {
    flushQuote(lines.length);
  }

  return <div className="email-body-renderer">{elements}</div>;
}

export default EmailBodyRenderer;
