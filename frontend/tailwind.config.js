/** @type {import('tailwindcss').Config} */

/**
 * Light, calm, low-contrast-chrome theme.
 *
 * The previous build was a dark control-room theme with saturated accents on
 * every surface, which made the whole page compete for attention: eight
 * provenance chips, six KPI cards, five chart series and a glowing hero all
 * shouting at the same volume. This palette is built so that **only data and
 * status carry colour** — every surface, border and label is a neutral, and
 * the reader's eye lands on the one thing that is actually wrong.
 *
 * Tokens are semantic, not numeric. `bg-surface-card` says what it is;
 * `bg-ink-800` said only how dark it was, which is how a theme drifts.
 */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // --- Surfaces: three levels, all near-white -----------------------
        surface: {
          page: '#f4f4f1', // the plane everything sits on
          card: '#ffffff', // raised content
          sunken: '#f4f4f1', // recessed panels inside a card
          hover: '#f8f8f6',
        },

        // --- Hairlines. One border weight, two strengths ------------------
        line: {
          DEFAULT: '#e5e4df',
          strong: '#cfcec8',
        },

        // --- Ink: exactly three text levels ------------------------------
        // Three is enough for any hierarchy and stops the page growing a
        // fourth and fifth shade of grey that nobody can tell apart.
        ink: {
          1: '#16161a', // headings, values
          2: '#52514e', // body
          3: '#87867f', // labels, captions, axis ticks
        },

        // --- Status: fills, marks and borders ----------------------------
        // Reserved. These never stand in for a chart series, and they are
        // always accompanied by a text label — never colour alone.
        status: {
          good: '#0ca30c',
          warn: '#fab219',
          serious: '#ec835a',
          critical: '#d03b3b',
          info: '#2a78d6',
        },

        // --- Status ink: the same roles, stepped dark enough for TEXT -----
        // The fill steps above are deliberately saturated for marks, and
        // several sit under 3:1 on a white surface (warning is 1.79:1). Small
        // text uses these instead, so a status word is always readable.
        'status-ink': {
          good: '#006300',
          warn: '#8a5a00',
          serious: '#a63a12',
          critical: '#a32020',
          info: '#1c5cab',
        },

        // --- Chart tokens (validated against #ffffff) --------------------
        series: {
          1: '#2a78d6',
          2: '#eb6834',
          3: '#1baf7a',
        },
        grid: '#ecebe6',
        axis: '#cfcec8',
      },
      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'sans-serif',
        ],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      boxShadow: {
        // One card shadow, barely there. Depth comes from the hairline.
        card: '0 1px 2px 0 rgba(22, 22, 26, 0.04)',
        raised: '0 2px 8px -2px rgba(22, 22, 26, 0.10)',
      },
      borderRadius: {
        card: '10px',
      },
    },
  },
  plugins: [],
}
