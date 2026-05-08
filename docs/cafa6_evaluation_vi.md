# Đánh Giá CAFA-6 Bằng CAFA-evaluator-PK

Tài liệu này mô tả cách đánh giá offline benchmark bằng evaluator chính thức
`CAFA-evaluator-PK`: https://github.com/claradepaolis/CAFA-evaluator-PK.

Wrapper trong repo:

```text
ml/evaluation/cafa_pk_official.py
scripts/run_cafa_pk_eval.py
```

Wrapper không tự viết lại metric. Nó chuẩn hóa file input rồi gọi evaluator gốc.

## File notebook xuất ra

Notebook high-performance sau khi train sẽ tạo:

```text
cafa6_high_performance_artifacts/
  go_terms.json
  final_test_metrics.csv
  splits/
    train_ids.txt
    valid_ids.txt
    test_ids.txt
    split_summary.csv
  official_eval/
    train_ids.txt
    valid_ids.txt
    test_ids.txt
    terms_of_interest.tsv
    valid_ground_truth.tsv
    ground_truth.tsv
    predictions/
      ensemble.tsv
    predictions_valid/
      ensemble_valid.tsv
```

Ý nghĩa:

- `splits/train_ids.txt`: protein dùng để train.
- `splits/valid_ids.txt`: protein dùng để early stopping và threshold tuning.
- `splits/test_ids.txt`: protein held-out cuối cùng.
- `splits/split_summary.csv`: thống kê phân bổ protein, annotation và aspect theo split.
- `final_test_metrics.csv`: metric nhanh trên test tại threshold được chọn từ validation.
- `test_ids.txt`: danh sách protein trong held-out test split.
- `terms_of_interest.tsv`: danh sách GO term mà model có thể dự đoán.
- `ground_truth.tsv`: nhãn thật của held-out proteins, lấy từ `train_terms.tsv`.
- `valid_ground_truth.tsv`: nhãn thật của validation split nếu muốn chạy evaluator
  riêng trên validation.
- `predictions/ensemble.tsv`: prediction cuối của ensemble ESM-MLP + ProtCNN +
  BiLSTM-Attention, và ProtBERT-MLP nếu nhánh này được bật.
- `predictions_valid/ensemble_valid.tsv`: prediction trên validation split.

Split mặc định là:

```text
train 70%
valid 15%
test  15%
```

Validation được dùng để early stopping và chọn threshold. Test chỉ dùng cho
đánh giá cuối cùng.

## Input CAFA-evaluator-PK yêu cầu

### Ontology file

```text
Train/go-basic.obo
```

### Prediction folder

Folder chứa một hoặc nhiều file prediction:

```text
official_eval/predictions/
  ensemble.tsv
```

Format mỗi dòng:

```text
ProteinID<TAB>GO_Term<TAB>Score
```

### Ground truth file

```text
ProteinID<TAB>GO_Term
```

Notebook đã tạo sẵn:

```text
official_eval/ground_truth.tsv
```

### Information accretion file

```text
IA.tsv
```

File này cần để evaluator sinh weighted metrics.

### Terms of interest

```text
official_eval/terms_of_interest.tsv
```

Vì model chỉ dự đoán selected label universe, nên nên truyền file này vào
`--terms-of-interest`. Nếu không, evaluator xét toàn bộ ontology và kết quả sẽ
khó diễn giải hơn.

### Known annotations

Không dùng mặc định trong split hiện tại. Nếu sau này mô phỏng Partial Knowledge,
có thể truyền thêm `--known-annotations`.

## Chuẩn bị CAFA-evaluator-PK

Cách 1, clone source:

```bash
git clone https://github.com/claradepaolis/CAFA-evaluator-PK.git /tmp/CAFA-evaluator-PK
```

Cách 2, cài trực tiếp nếu môi trường có internet:

```bash
pip install git+https://github.com/claradepaolis/CAFA-evaluator-PK.git
```

Trên Kaggle nếu tắt internet, hãy add source evaluator như Kaggle Dataset hoặc
upload folder evaluator kèm notebook.

## Chạy evaluator với output từ notebook

Ví dụ trên Kaggle:

```bash
python scripts/run_cafa_pk_eval.py run \
  --obo-file /kaggle/input/cafa-6-protein-function-prediction/Train/go-basic.obo \
  --prediction-dir /kaggle/working/cafa6_high_performance_artifacts/official_eval/predictions \
  --ground-truth /kaggle/working/cafa6_high_performance_artifacts/official_eval/ground_truth.tsv \
  --out-dir /kaggle/working/cafa6_high_performance_artifacts/official_eval/results \
  --ia-file /kaggle/input/cafa-6-protein-function-prediction/IA.tsv \
  --terms-of-interest /kaggle/working/cafa6_high_performance_artifacts/official_eval/terms_of_interest.tsv \
  --evaluator-src /tmp/CAFA-evaluator-PK \
  --threshold-step 0.01 \
  --threads 4
```

Nếu đã cài được package `cafaeval`, có thể bỏ `--evaluator-src`.

## Chạy evaluator trên validation split

Nếu muốn kiểm tra evaluator trước trên validation:

```bash
python scripts/run_cafa_pk_eval.py run \
  --obo-file /kaggle/input/cafa-6-protein-function-prediction/Train/go-basic.obo \
  --prediction-dir /kaggle/working/cafa6_high_performance_artifacts/official_eval/predictions_valid \
  --ground-truth /kaggle/working/cafa6_high_performance_artifacts/official_eval/valid_ground_truth.tsv \
  --out-dir /kaggle/working/cafa6_high_performance_artifacts/official_eval/results_valid \
  --ia-file /kaggle/input/cafa-6-protein-function-prediction/IA.tsv \
  --terms-of-interest /kaggle/working/cafa6_high_performance_artifacts/official_eval/terms_of_interest.tsv \
  --evaluator-src /tmp/CAFA-evaluator-PK \
  --threshold-step 0.01 \
  --threads 4
```

Folder validation được tách riêng để evaluator không đọc nhầm prediction test.

## Tạo input và chạy lại từ prediction TSV

Nếu muốn wrapper tự tạo `ground_truth.tsv` và `terms_of_interest.tsv` từ các file
gốc:

```bash
python scripts/run_cafa_pk_eval.py prepare-and-run \
  --train-terms /kaggle/input/cafa-6-protein-function-prediction/Train/train_terms.tsv \
  --test-ids /kaggle/working/cafa6_high_performance_artifacts/official_eval/test_ids.txt \
  --go-terms-json /kaggle/working/cafa6_high_performance_artifacts/go_terms.json \
  --prediction-tsv /kaggle/working/cafa6_high_performance_artifacts/official_eval/predictions/ensemble.tsv \
  --work-dir /kaggle/working/cafa6_high_performance_artifacts/official_eval \
  --method-name ensemble \
  --obo-file /kaggle/input/cafa-6-protein-function-prediction/Train/go-basic.obo \
  --ia-file /kaggle/input/cafa-6-protein-function-prediction/IA.tsv \
  --evaluator-src /tmp/CAFA-evaluator-PK \
  --threshold-step 0.01 \
  --threads 4
```

## Output cần đọc

Evaluator ghi:

```text
official_eval/results/
  evaluation_all.tsv
  evaluation_best_*.tsv
```

Các file `evaluation_best_*.tsv` chứa threshold tốt nhất theo từng metric. Nếu có
`IA.tsv`, ưu tiên weighted metrics vì đây là hướng gần CAFA hơn plain F1.

## Lưu ý diễn giải kết quả

Kết quả offline split không tương đương leaderboard thật:

- CAFA thật dùng prospective evaluation.
- Annotation GO có tính incomplete.
- Protein tương đồng có thể vẫn nằm ở cả train/test nếu chỉ split theo protein.

Kết quả này nên dùng để so sánh nội bộ giữa các model. Nếu muốn benchmark chặt
hơn, nên thêm taxonomy-aware hoặc sequence-similarity-aware split.
