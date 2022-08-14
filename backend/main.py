from fastapi import FastAPI, Query, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fpdf import FPDF, HTMLMixin
from enum import Enum
import pymysql.cursors
import uvicorn
import datetime
import os
from io import BytesIO


app = FastAPI(title="program kopearasi", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)
db_config = {
    "host": "localhost",
    "user": "root",
    "database": "program_koperasi",
    "cursorclass": pymysql.cursors.DictCursor,
}


class PDF(FPDF, HTMLMixin):
    pass


class Barang(BaseModel):
    nama_barang: str
    qty: int
    harga_beli: float
    harga_jual: float


class Pembeli(BaseModel):
    id_barang: int
    qty: int
    nama: str


class Interval(str, Enum):
    YEAR = "YEAR"
    MONTH = "MONTH"


class User(BaseModel):
    name: str = Field(..., max_length=50)
    username: str = Field(..., max_length=50, regex="^[a-zA-Z0-9_]*$")
    password: str = Field(..., max_length=50, regex="^[a-zA-Z0-9_@!]*$")

class Login(BaseModel):
    username: str = Field(..., max_length=50, regex="^[a-zA-Z0-9_]*$")
    password: str = Field(..., max_length=50, regex="^[a-zA-Z0-9_@!]*$")


def to_readable_num(num: int):
    num = str(num)[::-1]
    result = ''
    for i in range(len(num)):
        if (i+1)%3 == 0 and (i+1) != len(num):
            result = '.'+num[i]+result
        else:
            result = num[i]+result
    return 'Rp. '+result.replace('..00', ',_')


def connect_db():
    return pymysql.connect(**db_config)


def authenticate(token: str = Header(...)):
    if "user" in token and "authorize" in token:
        try:
            user_id = int(token.replace("user", "").replace("authorize", ""))
            status = ""
            with connect_db() as db:
                with db.cursor() as cursor:
                    cursor.execute("SELECT nama FROM user WHERE id_user=%s", (user_id,))
                    status = cursor.fetchone()
            if status is not None:
                return "VALID"
        except ValueError:
            pass
    return "INVALID"


@app.post("/login")
def login(
    user: Login,
    connection: object = Depends(connect_db),
):
    user_id = 0
    try: 
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id_user FROM user WHERE username=%s AND password=%s",
                    (user.username, user.password),
                )
                user_id = str(cursor.fetchone()['id_user'])
            return "user" + user_id + "authorize"
    except TypeError:
        return "FAILED"


@app.post("/new_item")
def new_item(
    barang: Barang,
    status: str = Depends(authenticate),
    connection: object = Depends(connect_db),
):
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO barang (nama_barang, qty, harga_beli, harga_jual)
				                VALUES (%s, %s, %s, %s)""",
                    (
                        barang.nama_barang,
                        barang.qty,
                        barang.harga_beli,
                        barang.harga_jual,
                    ),
                )
            connection.commit()
        return {"message": "Succesfully added new item. ", "status": "DONE"}
    except:
        return {"message": "adding new item failed. ", "status": "FAILED"}


@app.get("/get_items")
def get_item(
    jumlah: int | None = Query(default=None),
    status: str = Depends(authenticate),
    connection: object = Depends(connect_db),
):
    with connection:
        with connection.cursor() as cursor:
            if jumlah is not None:
                cursor.execute("SELECT * FROM barang WHERE deleted_on IS NULL LIMIT %s", (jumlah,))
            else:
                cursor.execute("SELECT * FROM barang WHERE deleted_on IS NULL")
            return cursor.fetchall()


@app.post("/beli")
def transaction(
    pembeli: Pembeli,
    status: str = Depends(authenticate),
    connection: object = Depends(connect_db),
):
    available_qty = 0
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT qty FROM barang WHERE id_barang=%s AND deleted_on IS NULL", (pembeli.id_barang,)
            )
            available_qty += cursor.fetchone()["qty"]
        if available_qty >= pembeli.qty:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
					INSERT INTO pembelian (nama_pembeli, id_barang, qty_pembelian) VALUES (%s, %s, %s)
					""",
                    (pembeli.nama, pembeli.id_barang, pembeli.qty),
                )
            connection.commit()

            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE barang SET qty=qty-%s WHERE id_barang=%s AND deleted_on IS NULL",
                    (pembeli.qty, pembeli.id_barang),
                )
            connection.commit()
    if available_qty >= pembeli.qty:
        return {"message": "Purchased Succesfully", "status": "DONE"}
    return {
        "message": "Request more Qty than available Qty.",
        "status": "FAILED",
        "available": available_qty,
    }


@app.put("/add_qty/{id_barang}")
def add_qty(
    id_barang,
    qty: int,
    status: str = Depends(authenticate),
    connection: object = Depends(connect_db),
):
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE barang SET qty=%s+qty WHERE id_barang=%s AND deleted_on IS NULL", (qty, id_barang)
                )
            connection.commit()
        return {"message": "Qty updated. ", "status": "DONE"}
    except:
        return {"message": "Qty fail updating. ", "status": "FAILED"}


@app.get("/transaction_history")
def transaction_history(from_: str | None = Query(None), to_: str | None = Query(None), 
    status: str = Depends(authenticate), connection: object = Depends(connect_db)
):
    result = list()
    with connection:
        with connection.cursor() as cursor:
            if from_ is not None and to_ is not None:
                cursor.execute("""
                    SELECT barang.nama_barang, pembelian.qty_pembelian, 
                    barang.harga_beli, barang.harga_jual, pembelian.nama_pembeli 
                    FROM pembelian JOIN barang ON 
                    pembelian.id_barang = barang.id_barang WHERE pembelian.tanggal_pembelian 
                    BETWEEN %s AND %s
                    """, (from_, to_))
                result = cursor.fetchall()
            else: 
                cursor.execute("""
                    SELECT barang.nama_barang, pembelian.qty_pembelian, 
                    barang.harga_beli, barang.harga_jual, pembelian.nama_pembeli 
                    FROM pembelian JOIN barang ON 
                    pembelian.id_barang = barang.id_barang""")
                result = cursor.fetchall()
    return result



@app.put("/update_item/{id_barang}")
def update_item(id_barang: int, barang: Barang, status: str = Depends(authenticate), connection: object = Depends(connect_db)):
	if status == "VALID":
		with connection:
			with connection.cursor() as cursor:
				cursor.execute('UPDATE barang SET nama_barang=%s, qty=%s, harga_beli=%s, harga_jual=%s WHERE id_barang=%s AND deleted_on IS NULL', 
					(barang.nama_barang, barang.qty, barang.harga_beli, barang.harga_jual,  id_barang))
			connection.commit()
			return {"message": "Data barang updated Succesfully. ", "status": "OK"}
	return status


@app.get("/get_profit")
def get_profit(from_: str | None = Query(None), to_: str | None = Query(None),
    status: str = Depends(authenticate), connection: object = Depends(connect_db)
):
    if status == "VALID":
        result = dict()
        with connection:
            with connection.cursor() as cursor:
                if from_ is not None and to_ is not None:
                   cursor.execute(
                        """SELECT (SUM(pembelian.qty_pembelian) * (barang.harga_jual - barang.harga_beli)) AS profit, barang.nama_barang, 
                        SUM(pembelian.qty_pembelian) AS qty_terjual
                        FROM pembelian 
                        INNER JOIN barang ON barang.id_barang=pembelian.id_barang 
                        WHERE pembelian.tanggal_pembelian BETWEEN %s AND %s  GROUP BY pembelian.id_barang"""
                    , (from_, to_))
                   result = cursor.fetchall()
                else: 
                    cursor.execute(
                        """SELECT (SUM(pembelian.qty_pembelian) * (barang.harga_jual - barang.harga_beli)) AS profit, barang.nama_barang, 
                        SUM(pembelian.qty_pembelian) AS qty_terjual
    					FROM pembelian 
    					INNER JOIN barang ON barang.id_barang=pembelian.id_barang GROUP BY pembelian.id_barang"""
                    )
                    result = cursor.fetchall()
        return result
    return status

@app.delete("/delete_item/{id_barang}")
def delete_item(id_barang: int, status: str = Depends(authenticate), connection: object = Depends(connect_db)):
    if status == "VALID":
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE barang SET deleted_on=NOW() WHERE id_barang=%s", (id_barang, ))
            connection.commit()
            return {"message": f"DELETED barang with id of: {id_barang}"}
    return status


@app.get("/report")
def report(
    from_: str | None = Query(default=None),
    to_: str | None = Query(default=None),
    status: str = Depends(authenticate),
    connection: object = Depends(connect_db),
):
    if status == 'VALID':
        def print_():
            html_text = f"""
                <h4 align='center'>Koperasi SMKN 5 Kota Tangerang</h4>
                <h2 align='center'><b>LAPORAN PENJUALAN PER BARANG</b></h2>
                <p align='center'>Dari {from_} s/d {to_}</p>
                <table width='100%'>
                <thead>
                    <tr>
                        <th width='20%'>Nama Barang</th>
                        <th width='20%'>Qty Terjual</th>
                        <th width='20%'>Modal</th>
                        <th width='20%'>Harga Jual</th>
                        <th width='20%'>Profit</th>
                    </tr>
                </thead>
                <tbody>
                """
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT barang.nama_barang, SUM(pembelian.qty_pembelian) AS qty_pembelian, barang.harga_beli, barang.harga_jual,SUM((pembelian.qty_pembelian) *
(barang.harga_jual - barang.harga_beli)) as profit FROM pembelian JOIN barang ON barang.id_barang=pembelian.id_barang WHERE pembelian.tanggal_pembelian BETWEEN %s AND %s GROUP BY barang.id_barang;
                        """, (from_, to_))
                    for data in cursor.fetchall():
                        html_text += f"""<tr>
                                            <td>{data['nama_barang']}</td>
                                            <td>{data['qty_pembelian']}</td>
                                            <td>{to_readable_num(data['harga_beli'])}</td>
                                            <td>{to_readable_num(data['harga_jual'])}</td>
                                            <td>{to_readable_num(data['profit'])}</td>
                                        </tr>"""
                    cursor.execute("""SELECT SUM((pembelian.qty_pembelian) * (barang.harga_jual - barang.harga_beli)) AS total_profit 
                        FROM pembelian JOIN barang 
                        ON pembelian.id_barang=barang.id_barang WHERE tanggal_pembelian BETWEEN %s AND %s LIMIT 1""", (from_, to_))
                    html_text += f"<tr><td colspan='4'><b>Total Profit</b></td><td>{to_readable_num(cursor.fetchone()['total_profit'])}</td></tr></tbody></table>"
            pdf = PDF()
            pdf.add_page()
            pdf.write_html(html_text, table_line_separators=True)
            # pdf.output(f'FILE_LAPORAN/laporan{str(datetime.datetime.now()).replace(" ", "").replace(".", "").replace(":", "")}.pdf')
            return BytesIO(pdf.output())
        try:
            return StreamingResponse(print_(), media_type="application/pdf")
        except TypeError:
            pass
    return status

if __name__ == '__main__':
    uvicorn.run(app)
