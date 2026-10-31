const messageForm = document.querySelector<HTMLFormElement>('#message-form')!;
const readForm = document.querySelector<HTMLFormElement>('#read-form')!;
const message = document.querySelector<HTMLInputElement>('#message')!;
const messageId = document.querySelector<HTMLInputElement>('#message-id')!;
const result = document.querySelector<HTMLParagraphElement>('#result')!;

type Message = { id: string; text: string; created_at: string };

async function requestMessage(url: string, options?: RequestInit): Promise<Message> {
  const response = await fetch(url, options);
  if (!response.ok) {
    if (response.status === 404) throw new Error('Message not found');
    if (response.status === 422) throw new Error('Enter a valid message or message ID');
    throw new Error('Unable to reach the message service');
  }
  return response.json() as Promise<Message>;
}

async function showMessage(form: HTMLFormElement, action: () => Promise<Message>) {
  const button = form.querySelector<HTMLButtonElement>('button')!;
  button.disabled = true;
  result.textContent = 'Loading…';
  try {
    const saved = await action();
    messageId.value = saved.id;
    result.textContent = saved.text;
  } catch (error) {
    result.textContent = error instanceof Error ? error.message : 'Message request failed';
  } finally {
    button.disabled = false;
  }
}

messageForm.addEventListener('submit', (event) => {
  event.preventDefault();
  void showMessage(messageForm, () => requestMessage('/api/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: message.value }),
  }));
});

readForm.addEventListener('submit', (event) => {
  event.preventDefault();
  void showMessage(readForm, () => requestMessage(`/api/messages/${encodeURIComponent(messageId.value.trim())}`));
});
