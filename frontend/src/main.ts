const button = document.querySelector<HTMLButtonElement>('#check-api');
const result = document.querySelector<HTMLParagraphElement>('#result');

if (!button || !result) {
  throw new Error('Page controls are missing');
}

button.addEventListener('click', async () => {
  result.textContent = 'Checking…';

  try {
    const response = await fetch('/api/message');
    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }

    const body: { message: string } = await response.json();
    result.textContent = body.message;
  } catch {
    result.textContent = 'API check failed';
  }
});
