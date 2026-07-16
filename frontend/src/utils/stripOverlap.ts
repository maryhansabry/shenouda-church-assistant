// محرك التعرف على الصوت (خصوصًا مع ar-EG) بيعمل أحيانًا "resegmentation":
// بيرجع يفسر جزء من الكلام اللي فات ويطلعه كـ isFinal تاني في index جديد،
// فبيتكرر جزء من النص حتى لو الـ index نفسه لم يتكرر.
// الدالة دي بتشيل أي تداخل (overlap) بين آخر كلمات في الـ buffer وأول كلمات القطعة الجديدة.
export function stripOverlap(bufferText: string, newChunk: string): string {
  const bufferWords = bufferText.trim().split(/\s+/).filter(Boolean);
  const newWords = newChunk.trim().split(/\s+/).filter(Boolean);

  if (bufferWords.length === 0 || newWords.length === 0) return newChunk;

  const maxOverlap = Math.min(bufferWords.length, newWords.length, 12); // حد أقصى معقول للبحث
  let overlapLen = 0;

  for (let len = maxOverlap; len > 0; len--) {
    const bufferSuffix = bufferWords.slice(-len).join(' ');
    const newPrefix = newWords.slice(0, len).join(' ');
    if (bufferSuffix === newPrefix) {
      overlapLen = len;
      break;
    }
  }

  return newWords.slice(overlapLen).join(' ');
}
