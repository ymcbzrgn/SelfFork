# Yamaç Jr. Nano — Kilitlenen Kararlar

Bu dosya, 16 GB RAM’li MacBook Pro üzerinde çalışacak **Yamaç Jr. Nano** mini sürümü için şu ana kadar birlikte alınan kararları özetler. Amaç, buradan sonraki ARGE ve uygulama konuşmasını Claude ile devam ettirirken tek parça referans kullanmaktır.

---

## 0. Proje pozisyonu

**Yamaç Jr. Nano**, büyük Yamaç Jr. vizyonunun düşük donanımda çalışacak ara/proof-of-concept sürümüdür.

Bu sürümün amacı:

- Büyük 48 GB Mac mini vizyonunu beklerken birkaç ay tatmin edici bir mini sürüm kurmak.
- Modelin Yamaç’ın mesaj üretme biçimini, itirazlarını, karar refleksini ve görev yönlendirme tarzını öğrenmesini sağlamak.
- Proje bazlı uzmanlıktan çok, “Yamaç nasıl düşünür ve ne yazar?” davranışını yakalamak.

Bu sürüm **tam otonom Yamaç Jr. değildir**. Ancak büyük sistemin kimlik/refleks katmanını küçük donanımda test eder.

---

# 1. Model ve context kararı

## Kilit karar

```text
Model: Gemma 4 E2B-it
Quantization: Q4_0 / 4-bit
Donanım: 16 GB RAM’li MacBook Pro
Context hedefi: 128K resmi limit
```

Başta 256K context istenmişti, fakat E2B sınıfı için resmi ve sağlam limit **128K** olarak kabul edildi.

## Karar sonucu

```text
256K context hedefinden vazgeçildi.
E2B Q4_0 ile 128K context kabul edildi.
```

---

# 2. Fine-tune yöntemi

## Kilit karar

```text
Gerçek full fine-tune yapılmayacak.
Q4_0 base model donmuş kalacak.
Üzerine güçlü bir adapter fine-tune edilecek.
```

Bu teknik olarak full fine-tune değildir. Ancak pratik hedef, modelin davranış olarak Yamaçlaşmasıdır.

## Karar sonucu

```text
Base model: Gemma 4 E2B-it Q4_0
Eğitilecek kısım: Yamaç adapter’ı
Ana ağırlıklar: Donmuş kalır
Hedef: Davranışsal Yamaçlaşma
```

---

# 3. Adapter’ın öğreneceği şey

## Kilit karar

İlk adapter sadece yazı tarzı öğrenmeyecek. En geniş hedef seçildi.

```text
Adapter hedefi:
Yazı tarzı + karar refleksi + görev yürütme refleksi
```

## Modelin öğrenmesi gereken davranışlar

Model şunları öğrenmeye çalışacak:

- Yamaç nasıl mesaj yazar?
- Yamaç ne zaman itiraz eder?
- Yamaç ne zaman acele karar verilmesine karşı çıkar?
- Yamaç teknik projeyi nasıl parçalara böler?
- Yamaç Claude Code / OpenCode gibi agent’ları nasıl yönlendirir?
- Yamaç ne zaman “dur, bu yanlış” der?
- Yamaç ne zaman kalite için daha zor yolu seçer?
- Yamaç kararları nasıl adım adım tartışır?

## Karar sonucu

```text
Basit persona adapter’ı yapılmayacak.
Mini PM/yönetici/refleks adapter’ı yapılacak.
```

---

# 4. Dataset kapsamı

## Kilit karar

Dataset küçük tutulmayacak. Geniş kapsamlı kaynaklardan beslenecek.

```text
Dataset kapsamı:
Yamaç mesajları + agent çıktıları + proje/repo bağlamı
```

Ancak daha sonra şu hassasiyet eklendi:

```text
Proje bazlı öğrenmesine gerek yok.
Beni tanısın yeter.
```

Bu nedenle proje/repo bilgisi ana öğrenme hedefi değil, gerektiğinde bağlam olacak.

## Karar sonucu

```text
Repo/proje bilgisi öğretmen değil.
Agent çıktısı öğretmen değil.
Yamaç mesajı hedef çıktı.
```

---

# 5. Target / hedef çıktı kararı

## Kilit karar

```text
Target sadece Yamaç’ın kendi mesajları olacak.
```

Agent cevapları, Claude Code çıktıları, OpenCode çıktıları, repo dosyaları, terminal logları ve proje bağlamı target olmayacak.

## Eğitim mantığı

```text
Context:
- Önceki konuşma
- Agent’ın verdiği cevap
- Proje/repo/terminal bağlamı, gerekiyorsa
- Daha önce alınan kararlar

Target:
- O anda Yamaç’ın gerçekten yazdığı mesaj
```

## Karar sonucu

Model şunu öğrenmeye çalışacak:

```text
“Bu bağlamda Yamaç ne yazardı?”
```

Modelin şunu öğrenmesi istenmiyor:

```text
“ChatGPT/Claude gibi cevap ver.”
```

---

# 6. Dataset formatı

## İlk eğilim

Chat formatı daha mantıklı bulundu.

## Revize karar

Chat formatı korunacak, fakat session-aware yapılacak.

```text
Dataset formatı:
Session-aware chat formatı
```

Her eğitim örneği, kendi session bağlamı içinde üretilecek.

## Örnek yapı

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are Yamaç Jr. Nano. Your task is to predict how Yamaç would respond in this situation."
    },
    {
      "role": "user",
      "content": "Previous session context:\n...\n\nAgent output:\n...\n\nWhat would Yamaç write next?"
    },
    {
      "role": "assistant",
      "content": "Yamaç’ın gerçek mesajı"
    }
  ]
}
```

Buradaki `assistant`, eğitim formatındaki hedef cevaptır. Bu, Claude’un veya başka bir agent’ın cevabı değildir. Yamaç Jr.’ın üretmesi gereken Yamaç mesajıdır.

---

# 7. Session-aware eğitim mantığı

## Kilit karar

Her mesaj bağımsız örnek gibi ele alınmayacak.

```text
Her Yamaç mesajı, kendi session bağlamı içinde eğitilecek.
```

Çünkü Yamaç her mesajı sıfırdan üretmiyor; önceki 3–10 mesajı, tartışmanın ritmini, daha önce alınan kararları ve karşı tarafın yaptığı hataları hatırlayarak yazıyor.

## Örnek

10 mesajlık bir session varsa:

```text
Sample 1:
Context: mesaj 1–2
Target: Yamaç mesajı 3

Sample 2:
Context: mesaj 1–4
Target: Yamaç mesajı 5

Sample 3:
Context: mesaj 1–6
Target: Yamaç mesajı 7
```

---

# 8. Context stratejisi

## Kilit karar

```text
Context stratejisi: Full session prefix
```

Rolling window veya hibrit özet kullanılmayacak. Her örnekte session başından hedef Yamaç mesajına kadar olan tüm konuşma context olarak verilecek.

## Karar sonucu

```text
Her Yamaç mesajı için:
- Aynı session’ın başından o ana kadar olan tüm konuşma context olarak verilir.
- Target sadece o andaki Yamaç mesajıdır.
```

Bu karar, Yamaç’ın session içi sürekliliğini modelin öğrenmesi için alındı.

---

# 9. Loss stratejisi

## İlk tartışma

İki basit seçenek vardı:

```text
A) Sadece son target Yamaç mesajına loss
B) Prefix içindeki tüm Yamaç mesajlarına loss
```

Yamaç, B’nin daha mantıklı olduğunu ama daha akıllı, risksiz hibrit bir çözüm gerektiğini belirtti.

## Kilit karar

```text
Hibrit Yamaç-only weighted loss kullanılacak.
```

## Loss ağırlıkları

```text
Agent / assistant / Claude Code / OpenCode mesajları: 0.0
Tool result / terminal çıktısı / repo context: 0.0
Önceki Yamaç mesajları: 0.3
Son hedef Yamaç mesajı: 1.0
```

## Karar gerekçesi

Bu yapı modelin şunları öğrenmesini sağlar:

- Session boyunca Yamaç nasıl bir çizgi tutturuyor?
- Önceki mesajlarını ve kararlarını nasıl sürdürüyor?
- Tartışmada nasıl yön değiştiriyor?
- Aynı session içinde tonu nasıl devam ettiriyor?
- En sonunda o bağlamda ne yazıyor?

Ama modelin agent/Claude/OpenCode cevaplarını taklit etmesini engeller.

---

# 10. Veri kaynakları

## Kilit karar

```text
Veri kaynakları: C seçeneği
```

Yani:

```text
Primary:
Claude Code + OpenCode sessionları

Secondary:
ChatGPT / Claude ARGE konuşmaları

Excluded / düşük değerli:
Alakasız günlük konuşmalar, çeviri, market, sağlık, oyun, rastgele kısa sorular
```

## Kaynak ağırlığı fikri

Henüz kesin implementasyon kararı değil, ama önerilen değerleme şudur:

```text
Claude Code / OpenCode agent yönetimi: yüksek değer
Teknik ARGE konuşmaları: orta-yüksek değer
Genel kişilik/yazı tarzı konuşmaları: düşük-orta değer
Alakasız gündelik konuşmalar: dataset dışı
```

## Amaç

Sadece kuru agent yöneticisi değil; Yamaç’ın karar verme, itiraz etme, kaliteyi savunma ve teknik tartışma tarzını da öğrenen bir adapter üretmek.

---

# 11. Ham veri toplama yaklaşımı

Bu aşama henüz tamamlanmadı. Claude ile devam edilecek bölüm burasıdır.

## Önerilen ham veri klasör yapısı

```bash
mkdir -p ~/yamac-jr-data/raw/claude-code
mkdir -p ~/yamac-jr-data/raw/opencode
mkdir -p ~/yamac-jr-data/raw/chatgpt
mkdir -p ~/yamac-jr-data/raw/claude-ai
```

## Claude Code verisi

Önerilen ilk kontrol:

```bash
ls -lah ~/.claude/projects/
```

Önerilen ham kopya:

```bash
cp -R ~/.claude/projects ~/yamac-jr-data/raw/claude-code/projects
```

Önerilen envanter komutları:

```bash
du -sh ~/yamac-jr-data/raw/claude-code/projects
find ~/yamac-jr-data/raw/claude-code/projects -name "*.jsonl" | wc -l
```

## OpenCode verisi

OpenCode için export mantığı ayrıca incelenecek. Hedef, mümkünse JSON export almak; Markdown export yalnızca insan kontrolü için yardımcı kaynak olabilir.

## ChatGPT verisi

ChatGPT export alınacaksa ham export doğrudan training’e sokulmayacak. Önce filtrelenecek.

Alınması muhtemel konuşmalar:

- Yamaç Jr.
- Gemma / fine-tune / RAG / agent konuşmaları
- Claude Code / OpenCode yönlendirme konuşmaları
- teknik proje karar konuşmaları
- ARGE tartışmaları

Dışarıda kalacak konuşmalar:

- çeviri
- gündelik Almanca
- oyun / CS2
- sağlık
- market / günlük yaşam
- rastgele kısa sorular

---

# 12. Şu ana kadar kesinleşen nihai karar seti

```text
1. Model:
Gemma 4 E2B-it Q4_0

2. Context:
128K resmi limit

3. Fine-tune tipi:
Q4_0 base + güçlü adapter fine-tune

4. Adapter hedefi:
Yazı tarzı + karar refleksi + görev yürütme refleksi

5. Dataset kapsamı:
Yamaç mesajları + agent çıktıları + gerektiği kadar proje/repo bağlamı

6. Target:
Sadece Yamaç’ın kendi mesajları

7. Dataset formatı:
Session-aware chat formatı

8. Context stratejisi:
Full session prefix

9. Loss stratejisi:
Yamaç-only weighted loss

10. Loss ağırlığı:
Agent/tool/context: 0.0
Önceki Yamaç mesajları: 0.3
Son hedef Yamaç mesajı: 1.0

11. Veri kaynakları:
Claude Code + OpenCode primary
ChatGPT / Claude ARGE konuşmaları secondary
Alakasız konuşmalar dışarıda
```

---

# 13. Claude ile devam edilecek açık konular

## A. Veri envanteri

- Claude Code session JSONL dosyaları nerede?
- Kaç session var?
- Toplam ham veri boyutu ne?
- OpenCode session/export formatı pratikte nasıl çıkıyor?
- ChatGPT export dosya yapısı nasıl ayrıştırılacak?

## B. Normalizasyon pipeline’ı

Ham kaynaklar şu forma çevrilecek:

```text
session_id
turn_index
timestamp
source
role
content
tool_calls
tool_results
project_path
metadata
```

## C. Yamaç mesajı tespiti

- Claude Code’da Yamaç mesajları nasıl ayrılacak?
- OpenCode’da user mesajları nasıl ayrılacak?
- ChatGPT export’ta Yamaç mesajları nasıl çıkarılacak?

## D. Training sample üretimi

Her Yamaç mesajı için:

```text
Context = session başından o ana kadar tüm konuşma
Target = o andaki Yamaç mesajı
Loss = weighted Yamaç-only loss
```

## E. Uzun session problemi

Full session prefix kararı alındı. Ancak teknik implementasyonda 128K sınır aşılırsa ne yapılacağı ayrıca tartışılmalı.

Şimdilik prensip:

```text
Full prefix ana kuraldır.
128K aşımı teknik zorunluluk olarak ayrıca ele alınır.
```

## F. Adapter eğitim altyapısı

Henüz karar verilmedi:

- MLX LoRA mı?
- Unsloth mı?
- Başka bir adapter training pipeline mı?
- MacBook’ta mı eğitilecek, yoksa geçici cloud mu kullanılacak?

Bu konu bilinçli olarak sonraya bırakıldı.

---

# 14. Projenin ruhu

Bu mini sürümde bile kolaya kaçılmayacak.

Yamaç’ın net pozisyonu:

```text
“Tam olsun, bizim olsun.”
“Kolaya kaçmak istemem.”
“Beni tanısın yeter.”
“Her mesaj benim için sıfırdan gelmiyor; session bağlamını hatırlıyorum.”
```

Bu yüzden sistemin ana felsefesi:

```text
Model bilgi ezberleyen bir repo asistanı değil.
Model, Yamaç’ın bağlam içindeki mesaj üretme refleksini öğrenen bir adapter taşıyıcısı olacak.
```
