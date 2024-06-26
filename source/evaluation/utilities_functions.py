from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import numpy as np
from scipy.optimize import linear_sum_assignment
import scipy
from source.utilities.remap_label import remap_label

def evaluation_bin_segmentation(mask_pred: Image.Image, mask_gt: Image.Image) :
    """
    evaluate segmentation with tp, tn, fp, fn to calculate the recall, precision, dice jaccard
    :param result:
    :param ground_truth:
    :return:
    """
    pred_array = np.array(mask_pred)
    gt_array = np.array(mask_gt)
    pred_array[pred_array > 0] = 1
    gt_array[gt_array > 0] = 1
    tp = int(np.sum(pred_array * gt_array))  # total number of TP
    tn = pred_array.size - np.count_nonzero(pred_array + gt_array)  # total number of TN
    fp = np.count_nonzero(pred_array - gt_array == 1)  # total number of FP
    fn = np.count_nonzero(gt_array - pred_array == 1)  # total number of FN
    if np.sum(gt_array) != 0 and tp == 0:
        recall = 0
        precision = 0
        dice = 0
        jaccard = 0
    elif np.sum(gt_array) == 0:
        recall = np.nan
        precision = np.nan
        dice = np.nan
        jaccard = np.nan
    else :
        recall = (tp+1e-8)/(tp+fn+1e-8)
        precision = (tp+1e-8)/(tp+fp+1e-8)
        dice = (2*tp+1e-8)/(2*tp+fp+fn+1e-8)
        jaccard = dice / (2-dice)
    return recall, precision, dice, jaccard, tp, tn, fp, fn

def evaluation_detection(result_array, ground_truth_array):
    truth_connected_array, truth_ncomponents = scipy.ndimage.label(
        ground_truth_array)
    result_connected_array, result_ncomponents = scipy.ndimage.label(
        result_array)
    print(truth_ncomponents, result_ncomponents)
    tp_detection = 0
    fn_detection = 0
    fp_detection = 0
    for l in range(1,truth_ncomponents+1):
        truth_connected_array2 = truth_connected_array.copy()
        truth_connected_array2[truth_connected_array != l] = 0
        truth_connected_array2[truth_connected_array == l] = 1
        tp = int(np.sum(result_array * truth_connected_array2))  # total number of TP
        fn = np.count_nonzero(truth_connected_array2 - result_array == 1)  # total number of FN
        if tp / (tp + fn) >= 0.5:
            tp_detection += 1
        else:
            fn_detection += 1

    for l in range(1,result_ncomponents+1):
        result_connected_array2 = result_connected_array.copy()
        result_connected_array2[result_connected_array != l] = 0
        result_connected_array2[result_connected_array == l] = 1
        tp = int(np.sum(ground_truth_array * result_connected_array2))  # total number of TP
        fn = np.count_nonzero(result_connected_array2 - ground_truth_array == 1)  # total number of FN
        if fn / (tp + fn) >= 0.5:
            fp_detection += 1
        else:
            pass
    return tp_detection, fn_detection, fp_detection

def get_fast_pq(mask_pred: Image.Image, mask_gt: Image.Image, match_iou=0.5):
    """`match_iou` is the IoU threshold level to determine the pairing between
    GT instances `p` and prediction instances `g`. `p` and `g` is a pair
    if IoU > `match_iou`. However, pair of `p` and `g` must be unique
    (1 prediction instance to 1 GT instance mapping).
    If `match_iou` < 0.5, Munkres assignment (solving minimum weight matching
    in bipartite graphs) is caculated to find the maximal amount of unique pairing.
    If `match_iou` >= 0.5, all IoU(p,g) > 0.5 pairing is proven to be unique and
    the number of pairs is also maximal.

    Fast computation requires instance IDs are in contiguous orderding
    i.e [1, 2, 3, 4] not [2, 3, 6, 10]. Please call `remap_label` beforehand
    and `by_size` flag has no effect on the result.
    Returns:
        [dq, sq, pq]: measurement statistic
        [paired_true, paired_pred, unpaired_true, unpaired_pred]:
                      pairing information to perform measurement

    """
    assert match_iou >= 0.0, "Cant' be negative"
    pred = np.array(mask_pred)
    true = np.array(mask_gt)
    pred = remap_label(pred)
    true = remap_label(true)
    true = np.copy(true)
    pred = np.copy(pred)
    true_id_list = list(np.unique(true))
    pred_id_list = list(np.unique(pred))
    if true_id_list == [0] and pred_id_list == [0]:
        return None, None, None, None, None, None, None
    elif true_id_list == [0] and pred_id_list != [0]:
        return 0, 0, 0, 0, 0, 0, 0
    elif true_id_list != [0] and pred_id_list == [0]:
        return 0, 0, 0, 0, 0, 0, 0

    true_masks = [
        None,
    ]
    for t in true_id_list[1:]:
        t_mask = np.array(true == t, np.uint8)
        true_masks.append(t_mask)

    pred_masks = [
        None,
    ]
    for p in pred_id_list[1:]:
        p_mask = np.array(pred == p, np.uint8)
        pred_masks.append(p_mask)

    # prefill with value
    pairwise_iou = np.zeros(
        [len(true_id_list) - 1, len(pred_id_list) - 1], dtype=np.float64
    )

    # caching pairwise iou
    for true_id in true_id_list[1:]:  # 0-th is background
        t_mask = true_masks[true_id]
        pred_true_overlap = pred[t_mask > 0]
        pred_true_overlap_id = np.unique(pred_true_overlap)
        pred_true_overlap_id = list(pred_true_overlap_id)
        for pred_id in pred_true_overlap_id:
            if pred_id == 0:  # ignore
                continue  # overlaping background
            p_mask = pred_masks[pred_id]
            total = (t_mask + p_mask).sum()
            inter = (t_mask * p_mask).sum()
            iou = inter / (total - inter)
            pairwise_iou[true_id - 1, pred_id - 1] = iou
    #
    if match_iou >= 0.5:
        paired_iou = pairwise_iou[pairwise_iou > match_iou]
        pairwise_iou[pairwise_iou <= match_iou] = 0.0
        paired_true, paired_pred = np.nonzero(pairwise_iou)
        paired_iou = pairwise_iou[paired_true, paired_pred]
        paired_true += 1  # index is instance id - 1
        paired_pred += 1  # hence return back to original
    else:  # * Exhaustive maximal unique pairing
        #### Munkres pairing with scipy library
        # the algorithm return (row indices, matched column indices)
        # if there is multiple same cost in a row, index of first occurence
        # is return, thus the unique pairing is ensure
        # inverse pair to get high IoU as minimum
        paired_true, paired_pred = linear_sum_assignment(-pairwise_iou)
        ### extract the paired cost and remove invalid pair
        paired_iou = pairwise_iou[paired_true, paired_pred]

        # now select those above threshold level
        # paired with iou = 0.0 i.e no intersection => FP or FN
        paired_true = list(paired_true[paired_iou > match_iou] + 1)
        paired_pred = list(paired_pred[paired_iou > match_iou] + 1)
        paired_iou = paired_iou[paired_iou > match_iou]

    # get the actual FP and FN
    unpaired_true = [idx for idx in true_id_list[1:] if idx not in paired_true]
    unpaired_pred = [idx for idx in pred_id_list[1:] if idx not in paired_pred]
    # print(paired_iou.shape, paired_true.shape, len(unpaired_true), len(unpaired_pred))

    #
    tp = len(paired_true)
    fp = len(unpaired_pred)
    fn = len(unpaired_true)
    # get the F1-score i.e DQ
    dq = tp / (tp + 0.5 * fp + 0.5 * fn)
    # get the SQ, no paired has 0 iou so not impact
    sq = paired_iou.sum() / (tp + 1.0e-6)

    return dq, sq, dq * sq, paired_true, paired_pred, unpaired_true, unpaired_pred