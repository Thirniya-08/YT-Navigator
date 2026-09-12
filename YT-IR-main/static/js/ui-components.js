/**
 * YT NAVIGATOR - Modern UI System
 * JavaScript Utilities & Interactive Components
 */

// ============================================
// UTILITY FUNCTIONS
// ============================================

/**
 * Utility object containing common helper functions
 */
const UIUtils = {
  /**
   * Show a toast notification
   * @param {string} message - Notification message
   * @param {string} type - 'success', 'error', 'info', 'warning'
   * @param {number} duration - Duration in ms (default: 3000)
   */
  toast: function (message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    const bgColor = {
      success: '#10B981',
      error: '#EF4444',
      info: '#00FFF0',
      warning: '#DE1A58'
    }[type] || '#00FFF0';

    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: ${bgColor};
      color: white;
      padding: 16px 24px;
      border-radius: 12px;
      box-shadow: 0 10px 15px rgba(0, 0, 0, 0.15);
      font-size: 14px;
      font-weight: 500;
      z-index: 9999;
      animation: slideUp 300ms cubic-bezier(0.4, 0, 0.2, 1);
      max-width: 400px;
    `;

    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideDown 300ms cubic-bezier(0.4, 0, 0.2, 1)';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  },

  /**
   * Show loading skeleton
   * @param {HTMLElement} container - Container to fill with skeleton
   * @param {number} count - Number of skeleton items
   */
  showSkeleton: function (container, count = 3) {
    container.innerHTML = Array(count).fill(`
      <div class="card animate-pulse" style="background: rgba(51, 65, 85, 0.5);">
        <div style="height: 200px; background: rgba(71, 85, 105, 0.5); border-radius: 8px; margin-bottom: 16px;"></div>
        <div style="height: 16px; background: rgba(71, 85, 105, 0.5); border-radius: 4px; margin-bottom: 12px; width: 80%;"></div>
        <div style="height: 12px; background: rgba(71, 85, 105, 0.5); border-radius: 4px; width: 60%;"></div>
      </div>
    `).join('');
  },

  /**
   * Debounce function
   * @param {Function} func - Function to debounce
   * @param {number} wait - Wait time in ms
   * @returns {Function}
   */
  debounce: function (func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },

  /**
   * Throttle function
   * @param {Function} func - Function to throttle
   * @param {number} limit - Limit time in ms
   * @returns {Function}
   */
  throttle: function (func, limit = 300) {
    let inThrottle;
    return function (...args) {
      if (!inThrottle) {
        func.apply(this, args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  },

  /**
   * Animate element scroll to view
   * @param {HTMLElement} element - Element to scroll to
   */
  scrollIntoView: function (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
  },

  /**
   * Add fade-in animation to elements on scroll
   */
  observeOnScroll: function () {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.style.animation = 'slideUp 500ms cubic-bezier(0.4, 0, 0.2, 1) forwards';
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });

    document.querySelectorAll('.animate-on-scroll').forEach(el => {
      el.style.opacity = '0';
      observer.observe(el);
    });
  }
};

// ============================================
// INTERACTIVE COMPONENTS
// ============================================

/**
 * Search Input with AI Suggestions
 */
class SmartSearchInput {
  constructor(inputSelector, suggestionsSelector) {
    this.input = document.querySelector(inputSelector);
    this.suggestionsContainer = document.querySelector(suggestionsSelector);
    this.setup();
  }

  setup() {
    if (!this.input) return;

    // Debounced input handler
    this.input.addEventListener('input', UIUtils.debounce((e) => {
      const query = e.target.value.trim();
      if (query.length > 2) {
        this.showSuggestions(query);
      } else {
        this.hideSuggestions();
      }
    }, 300));

    // Click outside to close
    document.addEventListener('click', (e) => {
      if (!this.input.contains(e.target) && !this.suggestionsContainer?.contains(e.target)) {
        this.hideSuggestions();
      }
    });

    // Focus animation
    this.input.addEventListener('focus', () => {
      this.input.style.boxShadow = '0 0 30px rgba(124, 58, 237, 0.3)';
    });

    this.input.addEventListener('blur', () => {
      this.input.style.boxShadow = '';
    });
  }

  showSuggestions(query) {
    if (!this.suggestionsContainer) return;
    // Mock suggestions - replace with actual API call
    const suggestions = [
      `Search for "${query}" in video titles`,
      `Find "${query}" in transcripts`,
      `Topics containing "${query}"`
    ];

    this.suggestionsContainer.innerHTML = suggestions
      .map(suggestion => `
        <div class="suggestion-item" style="padding: 12px 16px; cursor: pointer; border-bottom: 1px solid rgba(51, 51, 51, 0.2); hover-bg: rgba(222, 26, 88, 0.1);">
          <i class="fas fa-search" style="color: #666666; margin-right: 8px;"></i>
          ${suggestion}
        </div>
      `).join('');

    this.suggestionsContainer.style.display = 'block';
  }

  hideSuggestions() {
    if (this.suggestionsContainer) {
      this.suggestionsContainer.style.display = 'none';
    }
  }
}

/**
 * Toggle Component
 */
class Toggle {
  constructor(toggleSelector, contentSelector) {
    this.toggle = document.querySelector(toggleSelector);
    this.content = document.querySelector(contentSelector);
    this.isOpen = false;
    this.setup();
  }

  setup() {
    if (!this.toggle || !this.content) return;

    this.toggle.addEventListener('click', () => {
      this.isOpen ? this.close() : this.open();
    });
  }

  open() {
    this.isOpen = true;
    this.content.style.maxHeight = this.content.scrollHeight + 'px';
    this.content.style.opacity = '1';
    this.toggle.setAttribute('aria-expanded', 'true');
  }

  close() {
    this.isOpen = false;
    this.content.style.maxHeight = '0';
    this.content.style.opacity = '0';
    this.toggle.setAttribute('aria-expanded', 'false');
  }

  toggle() {
    this.isOpen ? this.close() : this.open();
  }
}

/**
 * Modal Dialog Component
 */
class Modal {
  constructor(triggerSelector, modalSelector) {
    this.trigger = document.querySelector(triggerSelector);
    this.modal = document.querySelector(modalSelector);
    this.closeBtn = this.modal?.querySelector('[data-close]');
    this.setup();
  }

  setup() {
    if (!this.trigger || !this.modal) return;

    this.trigger.addEventListener('click', () => this.open());

    this.closeBtn?.addEventListener('click', () => this.close());

    // Close on overlay click
    this.modal.addEventListener('click', (e) => {
      if (e.target === this.modal) this.close();
    });

    // Close on ESC key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.close();
    });
  }

  open() {
    this.modal.style.display = 'flex';
    this.modal.style.animation = 'fadeIn 300ms cubic-bezier(0.4, 0, 0.2, 1)';
    document.body.style.overflow = 'hidden';
  }

  close() {
    this.modal.style.display = 'none';
    document.body.style.overflow = '';
  }
}

/**
 * Tab Component
 */
class Tabs {
  constructor(containerSelector) {
    this.container = document.querySelector(containerSelector);
    this.tabs = this.container?.querySelectorAll('[data-tab]');
    this.panels = this.container?.querySelectorAll('[data-panel]');
    this.setup();
  }

  setup() {
    if (!this.tabs || !this.panels) return;

    this.tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const panelId = tab.getAttribute('data-tab');
        this.activate(panelId);
      });
    });
  }

  activate(panelId) {
    // Deactivate all
    this.tabs.forEach(t => t.classList.remove('active'));
    this.panels.forEach(p => p.style.display = 'none');

    // Activate selected
    document.querySelector(`[data-tab="${panelId}"]`)?.classList.add('active');
    document.querySelector(`[data-panel="${panelId}"]`).style.display = 'block';
  }
}

/**
 * Lazy Loading Images
 */
class LazyImageLoader {
  constructor() {
    this.images = document.querySelectorAll('img[data-src]');
    this.setup();
  }

  setup() {
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            img.classList.add('animate-fadeIn');
            observer.unobserve(img);
          }
        });
      });

      this.images.forEach(img => observer.observe(img));
    } else {
      // Fallback for older browsers
      this.images.forEach(img => {
        img.src = img.dataset.src;
      });
    }
  }
}

/**
 * Notification System
 */
class NotificationCenter {
  constructor() {
    this.container = document.createElement('div');
    this.container.style.cssText = `
      position: fixed;
      top: 80px;
      right: 24px;
      z-index: 9998;
      max-width: 500px;
    `;
    document.body.appendChild(this.container);
  }

  show(message, type = 'info', duration = 4000) {
    const notification = document.createElement('div');
    const colors = {
      success: '#10B981',
      error: '#EF4444',
      info: '#00FFF0',
      warning: '#DE1A58'
    };

    notification.style.cssText = `
      background: ${colors[type] || colors.info};
      color: white;
      padding: 16px 20px;
      border-radius: 12px;
      margin-bottom: 12px;
      box-shadow: 0 10px 15px rgba(0, 0, 0, 0.15);
      animation: slideUp 300ms cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 14px;
    `;

    const icon = {
      success: 'check-circle',
      error: 'exclamation-circle',
      info: 'info-circle',
      warning: 'exclamation-triangle'
    }[type] || 'info-circle';

    notification.innerHTML = `
      <i class="fas fa-${icon}"></i>
      <span>${message}</span>
    `;

    this.container.appendChild(notification);

    if (duration) {
      setTimeout(() => {
        notification.style.animation = 'slideDown 300ms cubic-bezier(0.4, 0, 0.2, 1)';
        setTimeout(() => notification.remove(), 300);
      }, duration);
    }
  }
}

/**
 * Form Validator
 */
class FormValidator {
  constructor(formSelector) {
    this.form = document.querySelector(formSelector);
    this.fields = this.form?.querySelectorAll('input, textarea, select');
  }

  validate() {
    let isValid = true;

    this.fields?.forEach(field => {
      const value = field.value.trim();
      const required = field.hasAttribute('required');

      if (required && !value) {
        this.showError(field, 'This field is required');
        isValid = false;
      } else if (field.type === 'email' && value && !this.isValidEmail(value)) {
        this.showError(field, 'Please enter a valid email');
        isValid = false;
      } else {
        this.clearError(field);
      }
    });

    return isValid;
  }

  isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  showError(field, message) {
    field.style.borderColor = '#DE1A58';
    field.style.boxShadow = '0 0 0 3px rgba(222, 26, 88, 0.1)';

    let errorElement = field.nextElementSibling;
    if (!errorElement?.classList.contains('form-error')) {
      errorElement = document.createElement('div');
      errorElement.className = 'form-error';
      field.parentNode.insertBefore(errorElement, field.nextSibling);
    }
    errorElement.textContent = message;
  }

  clearError(field) {
    field.style.borderColor = '';
    field.style.boxShadow = '';

    const errorElement = field.nextElementSibling;
    if (errorElement?.classList.contains('form-error')) {
      errorElement.remove();
    }
  }
}

/**
 * Smooth Scroll Spy - Highlight nav links based on scroll position
 */
class ScrollSpy {
  constructor(navSelector, contentsSelector) {
    this.nav = document.querySelector(navSelector);
    this.contents = document.querySelectorAll(contentsSelector);
    this.setup();
  }

  setup() {
    document.addEventListener('scroll', UIUtils.throttle(() => {
      let current = '';

      this.contents.forEach(section => {
        const sectionTop = section.offsetTop;
        const sectionHeight = section.clientHeight;

        if (scrollY >= sectionTop - 200) {
          current = section.getAttribute('id');
        }
      });

      this.nav?.querySelectorAll('a').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href').slice(1) === current) {
          link.classList.add('active');
        }
      });
    }, 100));
  }
}

// ============================================
// INITIALIZATION
// ============================================

/**
 * Initialize all UI components when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function () {
  // Observe elements for scroll animation
  UIUtils.observeOnScroll();

  // Initialize lazy image loading
  new LazyImageLoader();

  // Initialize notification center
  window.notificationCenter = new NotificationCenter();

  // Auto-initialize components with data attributes
  document.querySelectorAll('[data-toggle]').forEach(el => {
    const target = el.getAttribute('data-toggle');
    new Toggle(`[data-toggle="${target}"]`, `[data-toggle-content="${target}"]`);
  });

  document.querySelectorAll('[data-modal]').forEach(el => {
    const target = el.getAttribute('data-modal');
    new Modal(`[data-modal="${target}"]`, `#${target}`);
  });

  document.querySelectorAll('[data-tabs]').forEach(el => {
    new Tabs(`[data-tabs="${el.getAttribute('data-tabs')}"]`);
  });

  // Initialize forms
  document.querySelectorAll('form[data-validate]').forEach(form => {
    const validator = new FormValidator(`#${form.id}`);
    form.addEventListener('submit', (e) => {
      if (!validator.validate()) {
        e.preventDefault();
      }
    });
  });
});

// ============================================
// HELPER FUNCTIONS FOR COMMON TASKS
// ============================================

/**
 * Add loading state to button
 */
function setButtonLoading(button, isLoading = true) {
  if (isLoading) {
    button.disabled = true;
    button.classList.add('loading');
    button.dataset.originalText = button.textContent;
    button.textContent = 'Loading...';
  } else {
    button.disabled = false;
    button.classList.remove('loading');
    button.textContent = button.dataset.originalText;
  }
}

/**
 * Copy text to clipboard
 */
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    UIUtils.toast('Copied to clipboard!', 'success');
  } catch (err) {
    UIUtils.toast('Failed to copy', 'error');
  }
}

/**
 * Format timestamp for display
 */
function formatTime(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

/**
 * Truncate text with ellipsis
 */
function truncateText(text, length = 100) {
  return text.length > length ? text.substring(0, length) + '...' : text;
}

/**
 * Get initials from name
 */
function getInitials(name) {
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase();
}

/**
 * Check if element is in viewport
 */
function isInViewport(element) {
  const rect = element.getBoundingClientRect();
  return (
    rect.top >= 0 &&
    rect.left >= 0 &&
    rect.bottom <= window.innerHeight &&
    rect.right <= window.innerWidth
  );
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    UIUtils,
    SmartSearchInput,
    Toggle,
    Modal,
    Tabs,
    LazyImageLoader,
    NotificationCenter,
    FormValidator,
    ScrollSpy
  };
}
