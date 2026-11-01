import { describe, it, expect, vi, beforeEach } from 'vitest';
import { copyText } from '../utils/clipboard';

describe('copyText utility', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('uses navigator.clipboard when available in secure context', async () => {
    window.isSecureContext = true;
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      configurable: true,
      writable: true,
    });

    const result = await copyText('https://test.link/abc');
    expect(result).toBe(true);
    expect(writeTextMock).toHaveBeenCalledWith('https://test.link/abc');
  });

  it('falls back to document.execCommand when navigator.clipboard is undefined', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
      writable: true,
    });

    const execCommandMock = vi.fn().mockReturnValue(true);
    document.execCommand = execCommandMock;

    const result = await copyText('https://fallback.link/xyz');
    expect(result).toBe(true);
    expect(execCommandMock).toHaveBeenCalledWith('copy');
  });
});
