# Solution CAFA-6 High-Performance

Tài liệu này mô tả notebook
`cafa6/cafa6_offline_realtime_solution.ipynb` sau khi chuyển sang hướng
competition-style performance. Trọng tâm hiện tại là chất lượng dự đoán offline,
chưa tối ưu latency hay footprint cho production.

## Mục tiêu

CAFA-6 yêu cầu dự đoán nhiều GO term cho mỗi protein từ amino acid sequence.
Mỗi GO term thuộc một trong ba ontology:

- `MF`: Molecular Function.
- `BP`: Biological Process.
- `CC`: Cellular Component.

Bài toán là multi-label classification với số nhãn lớn, mất cân bằng mạnh và
GO graph có quan hệ phân cấp. Notebook hiện tại tạo một benchmark nội bộ bằng
cách tách held-out test split từ `Train`.

## Dữ liệu đầu vào

Notebook sử dụng các file:

- `Train/train_sequences.fasta`
- `Train/train_terms.tsv`
- `Train/train_taxonomy.tsv`
- `Train/go-basic.obo`
- `IA.tsv`
- `Test/testsuperset.fasta` nếu muốn thử batch inference sau training

Notebook tự tìm dataset trong Kaggle, ví dụ:

```text
/kaggle/input/cafa-6-protein-function-prediction
```

## EDA

Phần EDA bám theo notebook solution ban đầu:

- phân bố annotation theo `MF/BP/CC`
- số unique GO term mỗi aspect
- coverage protein mỗi aspect
- phân bố độ dài sequence
- power-law/long-tail của tần suất GO term
- số annotation trên mỗi protein
- top GO terms phổ biến

EDA nhằm xác nhận hai đặc điểm chính của bài toán: multi-label phức tạp và label
imbalance rất lớn.

## Tách train/validation/test

Vì competition đã đóng, notebook tạo offline benchmark từ train data.

Nguyên tắc split:

- Split theo protein ID, không split theo từng dòng annotation.
- Một protein không xuất hiện ở nhiều hơn một split.
- Stratification đơn giản theo tổ hợp aspect và số lượng annotation.

Tỉ lệ mặc định:

```python
train = 70%
validation = 15%
test = 15%
```

Vai trò từng split:

- `train`: fit model.
- `valid`: early stopping, learning-rate scheduling, threshold tuning và chọn
  threshold tốt nhất cho ensemble.
- `test`: held-out cuối cùng, chỉ dùng để report metric sau khi threshold đã
  được chọn từ validation và để xuất prediction cho CAFA-evaluator-PK.

Split này chưa nghiêm ngặt bằng sequence-similarity split, nhưng phù hợp để chạy
nhanh và so sánh các phiên bản model.

Notebook ghi rõ phân bổ split ra output:

```text
cafa6_high_performance_artifacts/
  splits/
    train_ids.txt
    valid_ids.txt
    test_ids.txt
    split_summary.csv
```

Các file này có thể tải về từ Kaggle output để tái lập split hoặc chạy evaluator
ngoài notebook.

## Không gian nhãn

Notebook tăng label space so với baseline nhẹ trước đó:

```python
max_labels = 3000
min_label_freq = 8
```

Các GO term được chọn theo tần suất giảm dần sau khi lọc `min_label_freq`. Cách
này giúp model phủ nhiều term hơn, đổi lại training nặng hơn và prediction file
lớn hơn. Nếu GPU/RAM yếu, có thể giảm `max_labels` về `1000` hoặc `2000`.

## Kiến trúc model

Notebook hiện dùng ensemble gồm các model bám sát solution được đề xuất ban đầu.

### 1. ESM-2 Frozen Embedding + MLP

Đây là model chính.

Backbone mặc định:

```python
facebook/esm2_t30_150M_UR50D
```

Luồng xử lý:

```text
protein sequence
-> ESM-2 tokenizer
-> ESM-2 transformer frozen
-> mean pooling hidden states
-> embedding vector
-> MLP classifier
-> sigmoid scores cho GO terms
```

MLP head:

```text
Linear
BatchNorm
GELU
Dropout
Linear
BatchNorm
GELU
Dropout
Linear(num_go_terms)
```

Embedding được cache ra `.npy` trong artifact directory để tránh chạy lại ESM
nhiều lần.

### 2. ProtCNN

ProtCNN dùng sequence index trực tiếp:

```text
amino acid indices
-> Embedding
-> Conv1D kernel 3
-> Conv1D kernel 5
-> Conv1D kernel 7
-> Concatenate
-> Conv1D 512
-> GlobalAveragePooling + GlobalMaxPooling
-> Dense head
-> sigmoid scores
```

Model này học motif/local pattern tốt và inference nhanh hơn transformer.

### 3. ProtBERT Frozen Embedding + MLP

Notebook có sẵn nhánh ProtBERT theo hướng solution ban đầu:

```python
Rostlab/prot_bert
```

Luồng xử lý giống ESM-MLP:

```text
protein sequence
-> ProtBERT tokenizer, amino acid cách nhau bằng khoảng trắng
-> ProtBERT frozen transformer
-> mean pooling hidden states
-> MLP classifier
-> sigmoid scores
```

Mặc định `train_protbert = False` vì ProtBERT khá nặng khi chạy cùng ESM-2 trên
Kaggle. Nếu muốn ensemble đủ cả bốn nhánh, bật:

```python
train_protbert = True
```

### 4. BiLSTM-Attention

BiLSTM-Attention dùng:

```text
amino acid indices
-> Embedding
-> BiLSTM
-> MultiHeadAttention
-> residual + LayerNorm
-> BiLSTM
-> GlobalAveragePooling + GlobalMaxPooling
-> Dense head
-> sigmoid scores
```

Model này giúp bắt thêm dependency theo chiều sequence, nhưng nặng hơn ProtCNN.
Nếu thiếu VRAM, có thể tắt bằng:

```python
train_bilstm_attention = False
```

### 5. Ensemble

Prediction cuối là weighted average:

```python
esm_mlp = 0.60
protcnn = 0.25
bilstm_attention = 0.12
protbert_mlp = 0.18
```

Chỉ các model được bật mới tham gia ensemble, sau đó weight được normalize lại.

## Training

Loss:

```python
BCEWithLogitsLoss(pos_weight=...)
```

`pos_weight` được tính từ label frequency và clip bằng `pos_weight_clip` để giảm
ảnh hưởng của extreme rare labels.

Notebook log:

- số protein, GO terms và annotation rows
- coverage của selected labels
- phân bổ train/valid/test
- số annotation và density của target matrix theo split
- shape của target matrix
- tiến độ extract ESM embeddings
- loss từng epoch trên train
- validation micro F1, precision, recall trong training
- threshold tuning trên validation
- test metrics tại validation-selected threshold
- top prediction examples

Notebook vẽ các biểu đồ:

- EDA distribution: aspect, GO term frequency, sequence length, annotation count.
- Protein count theo split.
- Số selected GO terms/protein theo split.
- Sequence length theo split.
- Label density theo split.
- Training loss theo model.
- Validation micro F1 theo threshold.
- Probability distribution của ensemble trên validation và test.
- Validation/test metric comparison.
- Held-out test Precision@K và Recall@K.

## Artifact được lưu

Sau khi train, notebook lưu:

```text
cafa6_high_performance_artifacts/
  cafa6_high_performance_models.pt
  config.json
  go_terms.json
  go_metadata.json
  training_history.csv
  threshold_tuning.csv
  final_test_metrics.csv
  valid_ensemble_probabilities.npy
  test_ensemble_probabilities.npy
  splits/
    train_ids.txt
    valid_ids.txt
    test_ids.txt
    split_summary.csv
  embeddings/
    train_<esm_model>_labels3000_len1022.npy
    valid_<esm_model>_labels3000_len1022.npy
    test_<esm_model>_labels3000_len1022.npy
  branch_checkpoints/
    esm_mlp.pt
    protcnn.pt
    bilstm_attention.pt
    protbert_mlp.pt
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

File `official_eval/` là input trực tiếp cho CAFA-evaluator-PK.

Trong quá trình train, notebook cũng lưu checkpoint sau từng branch model vào
`branch_checkpoints/`. Việc này giúp nếu lỗi xảy ra sau khi một branch đã train
xong thì output của branch đó vẫn còn trong Kaggle output.

## Recovery Sau Khi Kaggle Save Version Bị Fail

Nếu run fail sau bước extract embeddings nhưng trước khi lưu model cuối:

- Không thể khôi phục trained weights nếu run đó chưa kịp ghi
  `branch_checkpoints/*.pt` hoặc `cafa6_high_performance_models.pt`.
- Có thể khôi phục và tái sử dụng ESM embeddings đã lưu trong:

```text
cafa6_high_performance_artifacts/
  embeddings/
    train_*.npy
    valid_*.npy
    test_*.npy
```

Cách dùng lại embeddings từ failed output trên Kaggle:

1. Mở notebook mới hoặc edit version hiện tại.
2. Add output của failed version làm Kaggle input.
3. Run notebook lại. Notebook sẽ tự tìm file embedding cache trong
   `/kaggle/input/**/embeddings`.
4. Nếu thấy log dạng `Loading cached train embeddings`, nghĩa là đã bỏ qua bước
   extract ESM và chỉ train lại classifier/sequence models.

Từ version đã patch, notebook sẽ lưu checkpoint sau từng branch:

```text
branch_checkpoints/
  esm_mlp.pt
  protcnn.pt
  bilstm_attention.pt
```

Vì vậy nếu lỗi xảy ra ở cuối pipeline, lần sau có thể bổ sung logic resume từ
branch checkpoint thay vì train lại branch đã xong.

## Load Lại Model Để Infer

Notebook có cell `Reload-from-artifacts inference helpers`. Cell này được thiết
kế để chạy lại trong một session mới, không cần giữ các biến training như
`model_states`, `selected_terms` hay `active_weights`.

Các file bắt buộc để infer lại:

```text
cafa6_high_performance_artifacts/
  cafa6_high_performance_models.pt
  config.json
  go_terms.json
  go_metadata.json
```

Trong đó:

- `cafa6_high_performance_models.pt`: trọng số các nhánh model đã train.
- `config.json`: cấu hình kiến trúc, tên ESM/ProtBERT backbone, threshold và
  ensemble weights.
- `go_terms.json`: thứ tự output label.
- `go_metadata.json`: aspect, tên GO term và metadata phục vụ hiển thị.

Ví dụ infer lại từ artifact directory:

```python
predictor = Cafa6HighPerformancePredictor(
    \"/kaggle/working/cafa6_high_performance_artifacts\"
)

preds = predictor.predict([
    (\"protein_1\", \"MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV\")
], top_k=50)

display(preds.head())
```

Lưu ý: nếu checkpoint có nhánh `esm_mlp` hoặc `protbert_mlp`, lúc infer vẫn cần
tải lại pretrained backbone tương ứng từ Hugging Face hoặc từ cache Kaggle/Colab.
File `.pt` chỉ chứa classifier/sequence-model weights của solution, không chứa
toàn bộ trọng số ESM/ProtBERT pretrained.

## Cấu hình tài nguyên

Notebook có cell bootstrap đầu tiên để chạy được trong Kaggle
`Save Version / Run All`:

- Target khuyến nghị: `T4 x2` hoặc `L4`.
- Bootstrap kiểm tra `nvidia-smi`, PyTorch CUDA arch list và smoke test trên các
  GPU nhìn thấy được.
- Notebook không tự cài lại PyTorch và không yêu cầu restart kernel, vì flow đó
  không phù hợp khi save version.
- Notebook không fallback CPU cho training high-performance, vì extract ESM trên
  CPU quá chậm.
- Nếu Kaggle cấp P100 `sm_60` nhưng PyTorch runtime không hỗ trợ `sm_60`,
  notebook sẽ dừng sớm và yêu cầu đổi accelerator sang `T4 x2` hoặc `L4`.

Nếu Kaggle bị hết VRAM:

- đổi ESM sang `facebook/esm2_t12_35M_UR50D`
- giảm `embedding_batch_size`
- tắt `train_bilstm_attention`
- giảm `max_labels`

Nếu gặp lỗi dạng:

```text
Tesla P100-PCIE-16GB with CUDA capability sm_60 is not compatible
CUDA error: no kernel image is available for execution on the device
```

Cách xử lý:

- đổi Kaggle Accelerator sang `T4 x2` hoặc `L4`;
- không dùng P100 cho save-version run với runtime PyTorch không hỗ trợ `sm_60`;
- nếu bắt buộc dùng P100 thì phải tự quản lý một notebook riêng có bước cài lại
  PyTorch rồi restart kernel thủ công, không phù hợp với notebook save-version
  này.

Nếu có GPU mạnh hơn:

- thử `facebook/esm2_t33_650M_UR50D`
- tăng `max_labels`
- tăng epoch
- bật `train_protbert = True`
- thêm ProtT5 embedding làm model ensemble riêng nếu muốn mở rộng tiếp
