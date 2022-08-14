export function convert_readable_num(str_num) {
	let num = str_num.toString();
	let result = "";
	let len = num.length;
	for (var i = len - 1; i >= 0; i--) {
		if ((len-i)%3 === 0 && i !== 0){
			result = '.' + num[i] + result;
		}else {
			result = num[i] + result;
		}
	}
	return "Rp. " + result;
}

export function convert_sys_num(str) {
	//
}