"""Render current merged-FLEURS evidence as Markdown/CSV. No inference or rescoring."""
import argparse,csv,json
from pathlib import Path

def main(root):
 manifest=json.loads((root/'merged_manifest.json').read_text(encoding='utf-8'))
 rows=[]
 for sample in manifest['samples']:
  p=root/'production'/sample['sample_id']/'result.json'
  result=json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}
  w=result.get('WER') or {};c=result.get('CER') or {}
  rows.append({'sample_id':sample['sample_id'],'language':sample['language'],'clips':sample['clip_count'],
   'duration_seconds':sample['duration_seconds'],'sha256':sample['sha256'],'status':result.get('status','PENDING_OR_RUNNING'),
   'meeting_id':result.get('meeting_id'),'canonical_transcript_id':result.get('canonical_transcript_id'),
   'WER':w.get('wer'),'CER':c.get('cer'),'word_substitutions':w.get('substitutions'),
   'word_deletions':w.get('deletions'),'word_insertions':w.get('insertions'),'reference_words':w.get('ref_word_count'),
   'character_substitutions':c.get('substitutions'),'character_deletions':c.get('deletions'),
   'character_insertions':c.get('insertions'),'reference_characters':c.get('ref_char_count'),
   'processing_seconds':result.get('processing_seconds'),'RTF':result.get('RTF'),
   'fresh_readback_matches_api':result.get('fresh_readback_matches_api'),
   'accuracy_status':result.get('accuracy_status','NOT VERIFIED')})
 with (root/'RESULTS.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 report=['# Merged and quantized FLEURS evaluation','',
 'This is a modified-input long-recording experiment, not the official individual-utterance FLEURS protocol. Original 16-bit clips were concatenated and quantized to 8-bit; all 704 source clips/order/frames were verified before inference. No source audio was rewritten.',
 '', '| Language | Original clips | Seconds | Pipeline state | WER | CER |','|---|---:|---:|---|---:|---:|']
 def percent(value):return f'{value:.2%}' if value is not None else 'NOT VERIFIED'
 for row in rows:
  report.append(f"| {row['language']} | {row['clips']} | {row['duration_seconds']} | {row['status']} | {percent(row['WER'])} | {percent(row['CER'])} |")
 report+=['','## Method and limitations','',
 'Each file uses the existing REAL production API/worker path, with settings/source/model revision frozen in production/identity.json. Separate files execute sequentially on one GPU. Actual generated IDs and raw pipeline/events/readback are retained per file. No mock/fixture fallback or inferred success.',
 '', 'Reference: native transcription column from the matching local FLEURS test TSV, concatenated in verified waveform order. Normalization: NFC, casefold, retain Unicode letters/marks/numbers, punctuation to spaces, collapse whitespace; CER ignores whitespace. No translation/transliteration or guessed spelling correction. Exact aggregate edit counts are checked against RapidFuzz Levenshtein. WER/CER can exceed 100%; no invented accuracy percentage.',
 '', 'Metrics apply to the complete merged recording per language. They are not the arithmetic mean of clip WERs, nor independent utterance-level estimates. Clip edges do not provide word/speech onset annotations. DER/JER, acoustic language-ID accuracy and timestamp error are NOT VERIFIED for these files. No reference speaker identities were synthesized.',
 '', 'A failed or partial pipeline remains failed/partial even if a non-empty ASR transcript can be scored. Empty/missing outputs have no fabricated zero metric. Existing debug/repeated clips and the 8-bit conversion must be disclosed in a paper; do not pool these with original-utterance frozen-profile results or claim representative natural-meeting accuracy.',
 '', 'See RESULTS.csv for edit counts, exact IDs, hashes, durations, readback and RTF; see REFERENCE_VALIDATION.md and merged_manifest.json for every source clip/reference interval. Pending results update as the background controller and F: evidence mirror run.','']
 (root/'REPORT.md').write_text('\n'.join(report),encoding='utf-8')

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);main(p.parse_args().root)
