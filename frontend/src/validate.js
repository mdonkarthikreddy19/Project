export const ACCEPT = 'image/png,image/jpeg,image/webp'
const MAX_BYTES = 12 * 1024 * 1024

export function validateImage(file) {
  if (!file) return 'No file selected.'
  if (file.type && !ACCEPT.split(',').includes(file.type)) {
    return 'That file type isn’t supported. Use a JPG, PNG or WebP screenshot.'
  }
  if (file.size > MAX_BYTES) return 'That file is over 12 MB. Send the original screenshot instead.'
  return null
}
